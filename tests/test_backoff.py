from __future__ import annotations

import contextlib
import itertools
import logging
import re
import sys
import threading
import unittest.mock
from typing import TYPE_CHECKING, Any, Literal

import pytest
from dirty_equals import IsFloat, IsInstance

import backoff
from tests.common import EventAppender, _save_target

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from backoff._typing import Details


@pytest.fixture(autouse=True)
def _patch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)


def test_on_predicate() -> None:
    @backoff.on_predicate(backoff.expo)
    def return_true(log: list[bool], n: int) -> bool:
        val = len(log) == n - 1
        log.append(val)
        return val

    log: list[bool] = []
    ret = return_true(log, 3)
    assert ret is True
    assert len(log) == 3


def test_on_predicate_max_tries() -> None:
    @backoff.on_predicate(backoff.expo, jitter=None, max_tries=3)
    def return_true(log: list[bool], n: int) -> bool:
        val = len(log) == n
        log.append(val)
        return val

    log: list[bool] = []
    ret = return_true(log, 10)
    assert ret is False
    assert len(log) == 3


def test_on_predicate_max_time(monkeypatch: pytest.MonkeyPatch) -> None:
    nows = [
        10.000005,
        9,
        1,
        0,
    ]

    def monotonic() -> float:
        return nows.pop()

    monkeypatch.setattr("time.monotonic", monotonic)

    def giveup(details: Details) -> None:
        assert details["tries"] == 3
        assert details["elapsed"] == pytest.approx(10.000005)

    @backoff.on_predicate(backoff.expo, jitter=None, max_time=10, on_giveup=giveup)
    def return_true(log: list[bool], n: int) -> bool:
        val = len(log) == n
        log.append(val)
        return val

    log: list[bool] = []
    ret = return_true(log, 10)
    assert ret is False
    assert len(log) == 3


def test_on_predicate_max_time_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    nows = [
        10.000005,
        9,
        1,
        0,
    ]

    def monotonic() -> float:
        return nows.pop()

    monkeypatch.setattr("time.monotonic", monotonic)

    def giveup(details: Details) -> None:
        assert details["tries"] == 3
        assert details["elapsed"] == pytest.approx(10.000005)

    def lookup_max_time() -> int:
        return 10

    @backoff.on_predicate(
        backoff.expo,
        jitter=None,
        max_time=lookup_max_time,
        on_giveup=giveup,
    )
    def return_true(log: list[bool], n: int) -> bool:
        val = len(log) == n
        log.append(val)
        return val

    log: list[bool] = []
    ret = return_true(log, 10)
    assert ret is False
    assert len(log) == 3


def test_on_exception() -> None:
    @backoff.on_exception(backoff.expo, KeyError)
    def keyerror_then_true(log: list[Exception], n: int) -> Literal[True]:
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log: list[Exception] = []
    assert keyerror_then_true(log, 3) is True
    assert len(log) == 3


def test_on_exception_tuple() -> None:
    @backoff.on_exception(backoff.expo, (KeyError, ValueError))
    def keyerror_valueerror_then_true(log: list[Exception]) -> Literal[True]:
        e: Exception
        if len(log) == 2:
            return True
        if len(log) == 0:
            e = KeyError()
        if len(log) == 1:
            e = ValueError()
        log.append(e)
        raise e

    log: list[Exception] = []
    assert keyerror_valueerror_then_true(log) is True
    assert len(log) == 2
    assert isinstance(log[0], KeyError)
    assert isinstance(log[1], ValueError)


def test_on_exception_max_tries() -> None:
    @backoff.on_exception(backoff.expo, KeyError, jitter=None, max_tries=3)
    def keyerror_then_true(
        log: list[Exception],
        n: int,
        foo: str | None = None,
    ) -> Literal[True]:
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log: list[Exception] = []
    with pytest.raises(KeyError):
        keyerror_then_true(log, 10, foo="bar")

    assert len(log) == 3


def test_on_exception_max_tries_callable() -> None:
    @backoff.on_exception(backoff.expo, KeyError, jitter=None, max_tries=lambda: 3)
    def keyerror_then_true(
        log: list[Exception],
        n: int,
        foo: str | None = None,
    ) -> Literal[True]:
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log: list[Exception] = []
    with pytest.raises(KeyError):
        keyerror_then_true(log, 10, foo="bar")

    assert len(log) == 3


def test_on_exception_constant_iterable() -> None:
    appender = EventAppender()

    def on_backoff(details: Details) -> None:
        backoffs = appender.events["backoff"]
        assert details["tries"] == len(backoffs) + 1
        assert "exception" in details
        assert isinstance(details["exception"], KeyError)

        backoffs.append(details)

    def on_giveup(details: Details) -> None:
        giveups = appender.events["giveup"]
        assert details["tries"] == 4
        assert "exception" in details
        assert isinstance(details["exception"], KeyError)

        giveups.append(details)

    def on_success(details: Details) -> None:
        successes = appender.events["success"]

        successes.append(details)

    def on_try(details: Details) -> None:
        tries = appender.events["try"]

        tries.append(details)

    @backoff.on_exception(
        backoff.constant,
        KeyError,
        interval=(1, 2, 3),
        on_backoff=on_backoff,
        on_giveup=on_giveup,
        on_success=on_success,
        on_try=on_try,
    )
    def endless_exceptions() -> None:
        raise KeyError("foo")

    with pytest.raises(KeyError):
        endless_exceptions()

    assert appender.counts() == {
        "backoff": 3,
        "giveup": 1,
        "success": 0,
        "try": 4,
    }


def test_on_exception_success_random_jitter(appender: EventAppender) -> None:
    @backoff.on_exception(
        backoff.expo,
        Exception,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        jitter=backoff.random_jitter,
        factor=0.5,
    )
    @_save_target
    def succeeder(*args: Any, **kwargs: Any) -> None:
        # succeed after we've backed off twice
        if len(appender.events["backoff"]) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert appender.counts() == {
        "backoff": 2,
        "giveup": 0,
        "success": 1,
        "try": 3,
    }

    for i in range(2):
        details = appender.events["backoff"][i]
        assert details["wait"] >= 0.5 * 2**i


def test_on_exception_success_full_jitter(appender: EventAppender) -> None:
    @backoff.on_exception(
        backoff.expo,
        Exception,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        jitter=backoff.full_jitter,
        factor=0.5,
    )
    @_save_target
    def succeeder(*args: Any, **kwargs: Any) -> None:
        # succeed after we've backed off twice
        if len(appender.events["backoff"]) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert appender.counts() == {
        "backoff": 2,
        "giveup": 0,
        "success": 1,
        "try": 3,
    }

    for i in range(2):
        details = appender.events["backoff"][i]
        assert details["wait"] <= 0.5 * 2**i


def test_on_exception_success(appender: EventAppender) -> None:
    @backoff.on_exception(
        backoff.constant,
        Exception,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        jitter=None,
        interval=0,
    )
    @_save_target
    def succeeder(*args: Any, **kwargs: Any) -> None:
        # succeed after we've backed off twice
        if len(appender.events["backoff"]) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert appender.counts() == {
        "backoff": 2,
        "giveup": 0,
        "success": 1,
        "try": 3,
    }

    for i in range(2):
        details = appender.events["backoff"][i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
            "exception": IsInstance(ValueError),
        }

    details = appender.events["success"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "elapsed": IsFloat(gt=0),
    }


def test_on_exception_on_try_runs_before_attempt() -> None:
    calls: list[object] = []

    @backoff.on_exception(
        backoff.constant,
        ValueError,
        on_try=lambda details: calls.append((
            "try",
            details["tries"],
            details["elapsed"],
        )),
        jitter=None,
        interval=0,
        max_tries=3,
    )
    def fails() -> None:
        calls.append("call")
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        fails()

    assert calls == [
        ("try", 1, 0),
        "call",
        ("try", 2, IsFloat(gt=0)),
        "call",
        ("try", 3, IsFloat(gt=0)),
        "call",
    ]


@pytest.mark.parametrize("raise_on_giveup", [True, False])
def test_on_exception_giveup(raise_on_giveup: bool, appender: EventAppender) -> None:
    @backoff.on_exception(
        backoff.constant,
        ValueError,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        max_tries=3,
        jitter=None,
        raise_on_giveup=raise_on_giveup,
        interval=0,
    )
    @_save_target
    def exceptor(*args: Any, **kwargs: Any) -> None:
        raise ValueError("catch me")

    if raise_on_giveup:
        with pytest.raises(ValueError, match="catch me"):
            exceptor(1, 2, 3, foo=1, bar=2)
    else:
        exceptor(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice and giving up once
    assert appender.counts() == {
        "backoff": 2,
        "giveup": 1,
        "success": 0,
        "try": 3,
    }

    details = appender.events["giveup"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": exceptor._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "elapsed": IsFloat(gt=0),
        "exception": IsInstance(ValueError),
    }


def test_on_exception_giveup_predicate() -> None:
    def on_baz(e: Exception) -> bool:
        return str(e) == "baz"

    vals = ["baz", "bar", "foo"]

    @backoff.on_exception(backoff.constant, ValueError, giveup=on_baz)
    def foo_bar_baz() -> None:
        raise ValueError(vals.pop())

    with pytest.raises(ValueError, match=r"(baz|bar|foo)"):
        foo_bar_baz()

    assert not vals


def test_on_predicate_success(appender: EventAppender) -> None:
    @backoff.on_predicate(
        backoff.constant,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        jitter=None,
        interval=0,
    )
    @_save_target
    def success(*args: Any, **kwargs: Any) -> bool:
        # succeed after we've backed off twice
        return len(appender.events["backoff"]) == 2

    success(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert appender.counts() == {
        "backoff": 2,
        "giveup": 0,
        "success": 1,
        "try": 3,
    }

    for i in range(2):
        details = appender.events["backoff"][i]

        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "value": False,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
        }

    details = appender.events["success"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "value": True,
        "elapsed": IsFloat(gt=0),
    }


def test_on_predicate_on_try_runs_before_attempt() -> None:
    calls: list[object] = []

    @backoff.on_predicate(
        backoff.constant,
        on_try=lambda details: calls.append((
            "try",
            details["tries"],
            details["elapsed"],
        )),
        jitter=None,
        interval=0,
        max_tries=3,
    )
    def falsey() -> Literal[False]:
        calls.append("call")
        return False

    falsey()

    assert calls == [
        ("try", 1, 0),
        "call",
        ("try", 2, IsFloat(gt=0)),
        "call",
        ("try", 3, IsFloat(gt=0)),
        "call",
    ]


def test_on_predicate_giveup(appender: EventAppender) -> None:
    @backoff.on_predicate(
        backoff.constant,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        max_tries=3,
        jitter=None,
        interval=0,
    )
    @_save_target
    def emptiness(*args: Any, **kwargs: Any) -> None:
        pass

    emptiness(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice and giving up once
    assert appender.counts() == {
        "backoff": 2,
        "giveup": 1,
        "success": 0,
        "try": 3,
    }

    details = appender.events["giveup"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": emptiness._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "value": None,
        "elapsed": IsFloat(gt=0),
    }


def test_on_predicate_iterable_handlers() -> None:
    class Logger:
        def __init__(self) -> None:
            self.appender = EventAppender()

    loggers = [Logger() for _ in range(3)]

    @backoff.on_predicate(
        backoff.constant,
        on_backoff=(l.appender.on_event("backoff") for l in loggers),
        on_giveup=(l.appender.on_event("giveup") for l in loggers),
        on_success=(l.appender.on_event("success") for l in loggers),
        on_try=(l.appender.on_event("try") for l in loggers),
        max_tries=3,
        jitter=None,
        interval=0,
    )
    @_save_target
    def emptiness(*args: Any, **kwargs: Any) -> None:
        pass

    emptiness(1, 2, 3, foo=1, bar=2)

    for logger in loggers:
        assert logger.appender.counts() == {
            "backoff": 2,
            "giveup": 1,
            "success": 0,
            "try": 3,
        }

        details = logger.appender.events["giveup"][0]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": emptiness._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": 3,
            "value": None,
            "elapsed": IsFloat(gt=0),
        }


def test_on_exception_jitter(appender: EventAppender) -> None:
    @backoff.on_exception(
        backoff.constant,
        Exception,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        jitter=lambda value: 0.0,
        interval=0,
    )
    @_save_target
    def succeeder(*args: Any, **kwargs: Any) -> None:
        # succeed after we've backed off twice
        if len(appender.events["backoff"]) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert appender.counts() == {
        "backoff": 2,
        "giveup": 0,
        "success": 1,
        "try": 3,
    }

    for i in range(2):
        details = appender.events["backoff"][i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
            "exception": IsInstance(ValueError),
        }

    details = appender.events["success"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "elapsed": IsFloat(gt=0),
    }


def test_on_predicate_jitter(appender: EventAppender) -> None:
    @backoff.on_predicate(
        backoff.constant,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        jitter=lambda value: 0.0,
        interval=0,
    )
    @_save_target
    def success(*args: Any, **kwargs: Any) -> bool:
        # succeed after we've backed off twice
        return len(appender.events["backoff"]) == 2

    success(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert appender.counts() == {
        "backoff": 2,
        "giveup": 0,
        "success": 1,
        "try": 3,
    }

    for i in range(2):
        details = appender.events["backoff"][i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "value": False,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
        }

    details = appender.events["success"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "value": True,
        "elapsed": IsFloat(gt=0),
    }


def test_on_exception_callable_max_tries() -> None:
    log: list[bool] = []

    @backoff.on_exception(backoff.constant, ValueError, max_tries=lambda: 3)
    def exceptor() -> None:
        log.append(True)
        raise ValueError("aah")

    with pytest.raises(ValueError, match="aah"):
        exceptor()

    assert len(log) == 3


def test_on_exception_callable_max_tries_reads_every_time() -> None:
    lookups = []

    def lookup_max_tries() -> int:
        lookups.append(True)
        return 3

    @backoff.on_exception(backoff.constant, ValueError, max_tries=lookup_max_tries)
    def exceptor() -> None:
        raise ValueError("aah")

    with pytest.raises(ValueError, match="aah"):
        exceptor()

    with pytest.raises(ValueError, match="aah"):
        exceptor()

    assert len(lookups) == 2


def test_on_exception_callable_gen_kwargs() -> None:
    def lookup_foo() -> Literal["foo"]:
        return "foo"

    def wait_gen(
        foo: str | None = None,
        bar: str | None = None,
    ) -> Generator[float, None, None]:
        assert foo == "foo"
        assert bar == "bar"

        while True:
            yield 0

    @backoff.on_exception(wait_gen, ValueError, max_tries=2, foo=lookup_foo, bar="bar")
    def exceptor() -> None:
        raise ValueError("aah")

    with pytest.raises(ValueError, match="aah"):
        exceptor()


def test_on_predicate_in_thread() -> None:
    result: list[Exception | str] = []

    def check() -> None:
        try:

            @backoff.on_predicate(backoff.expo)
            def return_true(log: list[bool], n: int) -> bool:
                val = len(log) == n - 1
                log.append(val)
                return val

            log: list[bool] = []
            ret = return_true(log, 3)
            assert ret is True
            assert len(log) == 3

        except Exception as ex:  # ruff:ignore[blind-except]
            result.append(ex)
        else:
            result.append("success")

    t = threading.Thread(target=check)
    t.start()
    t.join()

    assert len(result) == 1
    assert result[0] == "success"


def test_on_predicate_constant_iterable(appender: EventAppender) -> None:
    waits = [1, 2, 3, 6, 9]

    @backoff.on_predicate(
        backoff.constant,
        interval=waits,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        jitter=None,
    )
    def falsey() -> Literal[False]:
        return False

    assert not falsey()
    assert appender.counts() == {
        "backoff": len(waits),
        "giveup": 1,
        "success": 0,
        "try": 6,
    }

    for i, wait in enumerate(waits):
        assert appender.events["backoff"][i]["wait"] == wait


def test_on_exception_in_thread() -> None:
    result: list[Exception | str] = []

    def check() -> None:
        try:

            @backoff.on_exception(backoff.expo, KeyError)
            def keyerror_then_true(log: list[Exception], n: int) -> Literal[True]:
                if len(log) == n:
                    return True
                e = KeyError()
                log.append(e)
                raise e

            log: list[Exception] = []
            assert keyerror_then_true(log, 3) is True
            assert len(log) == 3

        except Exception as ex:  # ruff:ignore[blind-except]
            result.append(ex)
        else:
            result.append("success")

    t = threading.Thread(target=check)
    t.start()
    t.join()

    assert len(result) == 1
    assert result[0] == "success"


def test_on_exception_logger_default(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("backoff")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)

    @backoff.on_exception(backoff.expo, KeyError, max_tries=3)
    def key_error() -> None:
        raise KeyError()

    with caplog.at_level(logging.INFO), pytest.raises(KeyError):
        key_error()

    assert len(caplog.records) == 3  # 2 backoffs and 1 giveup
    for record in caplog.records:
        assert record.name == "backoff"


def test_on_exception_logger_none(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("backoff")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)

    @backoff.on_exception(backoff.expo, KeyError, max_tries=3, logger=None)
    def key_error() -> None:
        raise KeyError()

    with caplog.at_level(logging.INFO), pytest.raises(KeyError):
        key_error()

    assert not caplog.records


def test_on_exception_logger_user(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("my-logger")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)

    @backoff.on_exception(backoff.expo, KeyError, max_tries=3, logger=logger)
    def key_error() -> None:
        raise KeyError()

    with caplog.at_level(logging.INFO), pytest.raises(KeyError):
        key_error()

    assert len(caplog.records) == 3  # 2 backoffs and 1 giveup
    for record in caplog.records:
        assert record.name == "my-logger"


def test_on_exception_logger_user_str(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("my-logger")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)

    @backoff.on_exception(backoff.expo, KeyError, max_tries=3, logger="my-logger")
    def key_error() -> None:
        raise KeyError()

    with caplog.at_level(logging.INFO), pytest.raises(KeyError):
        key_error()

    assert len(caplog.records) == 3  # 2 backoffs and 1 giveup
    for record in caplog.records:
        assert record.name == "my-logger"


def _on_exception_factory(
    backoff_log_level: int,
    giveup_log_level: int,
    max_tries: int,
) -> Callable[[], None]:
    @backoff.on_exception(
        backoff.expo,
        ValueError,
        max_tries=max_tries,
        backoff_log_level=backoff_log_level,
        giveup_log_level=giveup_log_level,
    )
    def value_error() -> None:
        raise ValueError("aah")

    def func() -> None:
        with pytest.raises(ValueError, match="aah"):
            value_error()

    return func


def _on_predicate_factory(
    backoff_log_level: int,
    giveup_log_level: int,
    max_tries: int,
) -> Callable[[], Literal[False]]:
    @backoff.on_predicate(
        backoff.expo,
        max_tries=max_tries,
        backoff_log_level=backoff_log_level,
        giveup_log_level=giveup_log_level,
    )
    def func() -> Literal[False]:
        return False

    return func


@pytest.mark.parametrize("func_factory", [_on_predicate_factory, _on_exception_factory])
@pytest.mark.parametrize(
    "backoff_log_level",
    [
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
    ],
)
@pytest.mark.parametrize(
    "giveup_log_level",
    [
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
    ],
)
def test_event_log_levels(
    caplog: pytest.LogCaptureFixture,
    func_factory: Callable[[int, int, int], Callable[[], Any]],
    backoff_log_level: int,
    giveup_log_level: int,
) -> None:
    max_tries = 3
    func = func_factory(backoff_log_level, giveup_log_level, max_tries)

    with (
        unittest.mock.patch("time.sleep", return_value=None),
        caplog.at_level(
            min(backoff_log_level, giveup_log_level),
            logger="backoff",
        ),
    ):
        func()

    backoff_re = re.compile(r"backing off", re.IGNORECASE)
    giveup_re = re.compile(r"giving up", re.IGNORECASE)

    backoff_log_count = 0
    giveup_log_count = 0
    for _logger_name, level, message in caplog.record_tuples:
        if level == backoff_log_level and backoff_re.match(message):
            backoff_log_count += 1
        elif level == giveup_log_level and giveup_re.match(message):
            giveup_log_count += 1

    assert backoff_log_count == max_tries - 1
    assert giveup_log_count == 1


def test_max_time(monkeypatch: pytest.MonkeyPatch) -> None:
    elapsed: float = 0

    def patch_sleep(n: float) -> None:
        nonlocal elapsed
        elapsed += n

    def monotonic() -> float:
        return elapsed

    monkeypatch.setattr("time.sleep", patch_sleep)
    monkeypatch.setattr("time.monotonic", monotonic)

    # A good place for property-based testing
    for function_runtime, max_time in itertools.product(range(10), repeat=2):
        elapsed = 0

        @backoff.on_exception(
            backoff.constant,
            RuntimeError,
            max_time=max_time,
            jitter=None,
        )
        def on_exception() -> None:
            patch_sleep(function_runtime)  # ruff: ignore[function-uses-loop-variable]
            raise RuntimeError

        with contextlib.suppress(BaseException):
            on_exception()

        # backoff never sleeps past max_time, but the time spent in the
        # target's own call isn't capped, so the total can run up to one
        # more function call past max_time before giving up.
        assert elapsed <= max_time + function_runtime + 1e-9

        elapsed = 0

        @backoff.on_predicate(
            backoff.constant,
            lambda x: False,
            max_time=max_time,
            jitter=None,
        )
        def on_predicate() -> None:
            patch_sleep(function_runtime)  # ruff: ignore[function-uses-loop-variable]

        on_predicate()
        assert elapsed <= max_time + function_runtime + 1e-9

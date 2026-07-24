from __future__ import annotations

import contextlib
import itertools
import logging
import re
import sys
import threading
import unittest.mock
from typing import TYPE_CHECKING

import pytest
from dirty_equals import IsFloat, IsInstance

import backoff
from tests.common import _save_target

if TYPE_CHECKING:
    from backoff._typing import Details


def test_on_predicate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    @backoff.on_predicate(backoff.expo)
    def return_true(log: list[bool], n):
        val = len(log) == n - 1
        log.append(val)
        return val

    log: list[bool] = []
    ret = return_true(log, 3)
    assert ret is True
    assert len(log) == 3


def test_on_predicate_max_tries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    @backoff.on_predicate(backoff.expo, jitter=None, max_tries=3)
    def return_true(log: list[bool], n):
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

    def monotonic():
        return nows.pop()

    monkeypatch.setattr("time.sleep", lambda x: None)
    monkeypatch.setattr("time.monotonic", monotonic)

    def giveup(details):
        assert details["tries"] == 3
        assert details["elapsed"] == pytest.approx(10.000005)

    @backoff.on_predicate(backoff.expo, jitter=None, max_time=10, on_giveup=giveup)
    def return_true(log: list[bool], n):
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

    def monotonic():
        return nows.pop()

    monkeypatch.setattr("time.sleep", lambda x: None)
    monkeypatch.setattr("time.monotonic", monotonic)

    def giveup(details):
        assert details["tries"] == 3
        assert details["elapsed"] == pytest.approx(10.000005)

    def lookup_max_time():
        return 10

    @backoff.on_predicate(
        backoff.expo, jitter=None, max_time=lookup_max_time, on_giveup=giveup
    )
    def return_true(log: list[bool], n):
        val = len(log) == n
        log.append(val)
        return val

    log: list[bool] = []
    ret = return_true(log, 10)
    assert ret is False
    assert len(log) == 3


def test_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    @backoff.on_exception(backoff.expo, KeyError)
    def keyerror_then_true(log: list[Exception], n):
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log: list[Exception] = []
    assert keyerror_then_true(log, 3) is True
    assert len(log) == 3


def test_on_exception_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    @backoff.on_exception(backoff.expo, (KeyError, ValueError))
    def keyerror_valueerror_then_true(log: list[Exception]):
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


def test_on_exception_max_tries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    @backoff.on_exception(backoff.expo, KeyError, jitter=None, max_tries=3)
    def keyerror_then_true(log: list[Exception], n, foo=None):
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log: list[Exception] = []
    with pytest.raises(KeyError):
        keyerror_then_true(log, 10, foo="bar")

    assert len(log) == 3


def test_on_exception_max_tries_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    @backoff.on_exception(backoff.expo, KeyError, jitter=None, max_tries=lambda: 3)
    def keyerror_then_true(log: list[Exception], n, foo=None):
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log: list[Exception] = []
    with pytest.raises(KeyError):
        keyerror_then_true(log, 10, foo="bar")

    assert len(log) == 3


def test_on_exception_constant_iterable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    def on_backoff(details: Details):
        nonlocal backoffs
        assert details["tries"] == len(backoffs) + 1
        assert "exception" in details
        assert isinstance(details["exception"], KeyError)

        backoffs.append(details)

    def on_giveup(details: Details):
        nonlocal giveups
        assert details["tries"] == 4
        assert "exception" in details
        assert isinstance(details["exception"], KeyError)

        giveups.append(details)

    def on_success(details: Details):
        nonlocal successes

        successes.append(details)

    @backoff.on_exception(
        backoff.constant,
        KeyError,
        interval=(1, 2, 3),
        on_backoff=on_backoff,
        on_giveup=on_giveup,
        on_success=on_success,
    )
    def endless_exceptions():
        raise KeyError("foo")

    with pytest.raises(KeyError):
        endless_exceptions()

    assert len(backoffs) == 3
    assert len(giveups) == 1
    assert len(successes) == 0


def test_on_exception_success_random_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_exception(
        backoff.expo,
        Exception,
        on_success=successes.append,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        jitter=backoff.random_jitter,
        factor=0.5,
    )
    @_save_target
    def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(backoffs) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(successes) == 1
    assert len(backoffs) == 2
    assert len(giveups) == 0

    for i in range(2):
        details = backoffs[i]
        assert details["wait"] >= 0.5 * 2**i


def test_on_exception_success_full_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_exception(
        backoff.expo,
        Exception,
        on_success=successes.append,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        jitter=backoff.full_jitter,
        factor=0.5,
    )
    @_save_target
    def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(backoffs) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(successes) == 1
    assert len(backoffs) == 2
    assert len(giveups) == 0

    for i in range(2):
        details = backoffs[i]
        assert details["wait"] <= 0.5 * 2**i


def test_on_exception_success() -> None:
    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_exception(
        backoff.constant,
        Exception,
        on_success=successes.append,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        jitter=None,
        interval=0,
    )
    @_save_target
    def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(backoffs) < 2:
            raise ValueError("catch me")

    succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(successes) == 1
    assert len(backoffs) == 2
    assert len(giveups) == 0

    for i in range(2):
        details = backoffs[i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
            "exception": IsInstance(ValueError),
        }

    details = successes[0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "elapsed": IsFloat(gt=0),
    }


@pytest.mark.parametrize("raise_on_giveup", [True, False])
def test_on_exception_giveup(raise_on_giveup: bool) -> None:
    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_exception(
        backoff.constant,
        ValueError,
        on_success=successes.append,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        max_tries=3,
        jitter=None,
        raise_on_giveup=raise_on_giveup,
        interval=0,
    )
    @_save_target
    def exceptor(*args, **kwargs):
        raise ValueError("catch me")

    if raise_on_giveup:
        with pytest.raises(ValueError, match="catch me"):
            exceptor(1, 2, 3, foo=1, bar=2)
    else:
        exceptor(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice and giving up once
    assert len(successes) == 0
    assert len(backoffs) == 2
    assert len(giveups) == 1

    details = giveups[0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": exceptor._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "elapsed": IsFloat(gt=0),
        "exception": IsInstance(ValueError),
    }


def test_on_exception_giveup_predicate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    def on_baz(e):
        return str(e) == "baz"

    vals = ["baz", "bar", "foo"]

    @backoff.on_exception(backoff.constant, ValueError, giveup=on_baz)
    def foo_bar_baz():
        raise ValueError(vals.pop())

    with pytest.raises(ValueError, match=r"(baz|bar|foo)"):
        foo_bar_baz()

    assert not vals


def test_on_predicate_success() -> None:
    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_predicate(
        backoff.constant,
        on_success=successes.append,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        jitter=None,
        interval=0,
    )
    @_save_target
    def success(*args, **kwargs):
        # succeed after we've backed off twice
        return len(backoffs) == 2

    success(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(successes) == 1
    assert len(backoffs) == 2
    assert len(giveups) == 0

    for i in range(2):
        details = backoffs[i]

        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "value": False,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
        }

    details = successes[0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "value": True,
        "elapsed": IsFloat(gt=0),
    }


def test_on_predicate_giveup() -> None:
    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_predicate(
        backoff.constant,
        on_success=successes.append,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        max_tries=3,
        jitter=None,
        interval=0,
    )
    @_save_target
    def emptiness(*args, **kwargs):
        pass

    emptiness(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice and giving up once
    assert len(successes) == 0
    assert len(backoffs) == 2
    assert len(giveups) == 1

    details = giveups[0]
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
        def __init__(self):
            self.backoffs: list[Details] = []
            self.giveups: list[Details] = []
            self.successes: list[Details] = []

    loggers = [Logger() for _ in range(3)]

    @backoff.on_predicate(
        backoff.constant,
        on_backoff=(l.backoffs.append for l in loggers),
        on_giveup=(l.giveups.append for l in loggers),
        on_success=(l.successes.append for l in loggers),
        max_tries=3,
        jitter=None,
        interval=0,
    )
    @_save_target
    def emptiness(*args, **kwargs):
        pass

    emptiness(1, 2, 3, foo=1, bar=2)

    for logger in loggers:
        assert len(logger.successes) == 0
        assert len(logger.backoffs) == 2
        assert len(logger.giveups) == 1

        details = logger.giveups[0]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": emptiness._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": 3,
            "value": None,
            "elapsed": IsFloat(gt=0),
        }


# To maintain backward compatibility,
# on_predicate should support 0-argument jitter function.
def test_on_exception_success_0_arg_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_exception(
        backoff.constant,
        Exception,
        on_success=successes.append,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        jitter=lambda: 0.0,  # type:ignore[arg-type,misc] # ty:ignore[invalid-argument-type]
        interval=0,
    )
    @_save_target
    def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(backoffs) < 2:
            raise ValueError("catch me")

    with pytest.deprecated_call(
        match="Nullary jitter function signature is deprecated",
    ):
        succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(successes) == 1
    assert len(backoffs) == 2
    assert len(giveups) == 0

    for i in range(2):
        details = backoffs[i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
            "exception": IsInstance(ValueError),
        }

    details = successes[0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "elapsed": IsFloat(gt=0),
    }


# To maintain backward compatibility,
# on_predicate should support 0-argument jitter function.
def test_on_predicate_success_0_arg_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_predicate(
        backoff.constant,
        on_success=successes.append,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        jitter=lambda: 0.0,  # type:ignore[arg-type,misc] # ty:ignore[invalid-argument-type]
        interval=0,
    )
    @_save_target
    def success(*args, **kwargs):
        # succeed after we've backed off twice
        return len(backoffs) == 2

    with pytest.deprecated_call(
        match="Nullary jitter function signature is deprecated",
    ):
        success(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(successes) == 1
    assert len(backoffs) == 2
    assert len(giveups) == 0

    for i in range(2):
        details = backoffs[i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "value": False,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
        }

    details = successes[0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "value": True,
        "elapsed": IsFloat(gt=0),
    }


def test_on_exception_callable_max_tries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    log: list[bool] = []

    @backoff.on_exception(backoff.constant, ValueError, max_tries=lambda: 3)
    def exceptor():
        log.append(True)
        raise ValueError("aah")

    with pytest.raises(ValueError, match="aah"):
        exceptor()

    assert len(log) == 3


def test_on_exception_callable_max_tries_reads_every_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    lookups = []

    def lookup_max_tries():
        lookups.append(True)
        return 3

    @backoff.on_exception(backoff.constant, ValueError, max_tries=lookup_max_tries)
    def exceptor():
        raise ValueError("aah")

    with pytest.raises(ValueError, match="aah"):
        exceptor()

    with pytest.raises(ValueError, match="aah"):
        exceptor()

    assert len(lookups) == 2


def test_on_exception_callable_gen_kwargs():
    def lookup_foo():
        return "foo"

    def wait_gen(foo=None, bar=None):
        assert foo == "foo"
        assert bar == "bar"

        while True:
            yield 0

    @backoff.on_exception(wait_gen, ValueError, max_tries=2, foo=lookup_foo, bar="bar")
    def exceptor():
        raise ValueError("aah")

    with pytest.raises(ValueError, match="aah"):
        exceptor()


def test_on_predicate_in_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    result: list[Exception | str] = []

    def check():
        try:

            @backoff.on_predicate(backoff.expo)
            def return_true(log: list[bool], n):
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


def test_on_predicate_constant_iterable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    waits = [1, 2, 3, 6, 9]
    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_predicate(
        backoff.constant,
        interval=waits,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        on_success=successes.append,
        jitter=None,
    )
    def falsey():
        return False

    assert not falsey()

    assert len(backoffs) == len(waits)
    for i, wait in enumerate(waits):
        assert backoffs[i]["wait"] == wait

    assert len(giveups) == 1
    assert len(successes) == 0


def test_on_exception_in_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    result: list[Exception | str] = []

    def check():
        try:

            @backoff.on_exception(backoff.expo, KeyError)
            def keyerror_then_true(log: list[Exception], n):
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


def test_on_exception_logger_default(monkeypatch, caplog):
    monkeypatch.setattr("time.sleep", lambda x: None)

    logger = logging.getLogger("backoff")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)

    @backoff.on_exception(backoff.expo, KeyError, max_tries=3)
    def key_error():
        raise KeyError()

    with caplog.at_level(logging.INFO), pytest.raises(KeyError):
        key_error()

    assert len(caplog.records) == 3  # 2 backoffs and 1 giveup
    for record in caplog.records:
        assert record.name == "backoff"


def test_on_exception_logger_none(monkeypatch, caplog):
    monkeypatch.setattr("time.sleep", lambda x: None)

    logger = logging.getLogger("backoff")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)

    @backoff.on_exception(backoff.expo, KeyError, max_tries=3, logger=None)
    def key_error():
        raise KeyError()

    with caplog.at_level(logging.INFO), pytest.raises(KeyError):
        key_error()

    assert not caplog.records


def test_on_exception_logger_user(monkeypatch, caplog):
    monkeypatch.setattr("time.sleep", lambda x: None)

    logger = logging.getLogger("my-logger")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)

    @backoff.on_exception(backoff.expo, KeyError, max_tries=3, logger=logger)
    def key_error():
        raise KeyError()

    with caplog.at_level(logging.INFO), pytest.raises(KeyError):
        key_error()

    assert len(caplog.records) == 3  # 2 backoffs and 1 giveup
    for record in caplog.records:
        assert record.name == "my-logger"


def test_on_exception_logger_user_str(monkeypatch, caplog):
    monkeypatch.setattr("time.sleep", lambda x: None)

    logger = logging.getLogger("my-logger")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)

    @backoff.on_exception(backoff.expo, KeyError, max_tries=3, logger="my-logger")
    def key_error():
        raise KeyError()

    with caplog.at_level(logging.INFO), pytest.raises(KeyError):
        key_error()

    assert len(caplog.records) == 3  # 2 backoffs and 1 giveup
    for record in caplog.records:
        assert record.name == "my-logger"


def _on_exception_factory(
    backoff_log_level,
    giveup_log_level,
    max_tries,
):
    @backoff.on_exception(
        backoff.expo,
        ValueError,
        max_tries=max_tries,
        backoff_log_level=backoff_log_level,
        giveup_log_level=giveup_log_level,
    )
    def value_error():
        raise ValueError("aah")

    def func():
        with pytest.raises(ValueError, match="aah"):
            value_error()

    return func


def _on_predicate_factory(
    backoff_log_level,
    giveup_log_level,
    max_tries,
):
    @backoff.on_predicate(
        backoff.expo,
        max_tries=max_tries,
        backoff_log_level=backoff_log_level,
        giveup_log_level=giveup_log_level,
    )
    def func():
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
    caplog,
    func_factory,
    backoff_log_level,
    giveup_log_level,
):
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
        def on_exception():
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
        def on_predicate():
            patch_sleep(function_runtime)  # ruff: ignore[function-uses-loop-variable]

        on_predicate()
        assert elapsed <= max_time + function_runtime + 1e-9

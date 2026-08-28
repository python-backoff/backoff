from __future__ import annotations

import asyncio
import contextlib
import itertools
from typing import TYPE_CHECKING

import pytest
from dirty_equals import IsFloat, IsInstance

import backoff
from tests.common import EventAppender, _save_target

if TYPE_CHECKING:
    from collections.abc import Generator


asyncio_sleep = asyncio.sleep


async def _await_none(x):
    return None


@pytest.fixture(autouse=True)
def _patch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)


@pytest.mark.asyncio
async def test_on_predicate() -> None:
    @backoff.on_predicate(backoff.expo)
    async def return_true(log, n):
        val = len(log) == n - 1
        log.append(val)
        return val

    log: list[bool] = []
    ret = await return_true(log, 3)
    assert ret is True
    assert len(log) == 3


@pytest.mark.asyncio
async def test_on_predicate_max_tries() -> None:
    @backoff.on_predicate(backoff.expo, jitter=None, max_tries=3)
    async def return_true(log, n):
        val = len(log) == n
        log.append(val)
        return val

    log: list[bool] = []
    ret = await return_true(log, 10)
    assert ret is False
    assert len(log) == 3


@pytest.mark.asyncio
async def test_on_predicate_max_tries_callable() -> None:
    @backoff.on_predicate(backoff.expo, jitter=None, max_tries=lambda: 3)
    async def return_true(log, n):
        val = len(log) == n
        log.append(val)
        return val

    log: list[bool] = []
    ret = await return_true(log, 10)
    assert ret is False
    assert len(log) == 3


@pytest.mark.asyncio
async def test_on_exception() -> None:
    @backoff.on_exception(backoff.expo, KeyError)
    async def keyerror_then_true(log, n):
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log: list[Exception] = []
    assert (await keyerror_then_true(log, 3)) is True
    assert len(log) == 3


@pytest.mark.asyncio
async def test_on_exception_tuple() -> None:
    @backoff.on_exception(backoff.expo, (KeyError, ValueError))
    async def keyerror_valueerror_then_true(log: list[Exception]):
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
    assert (await keyerror_valueerror_then_true(log)) is True
    assert len(log) == 2
    assert isinstance(log[0], KeyError)
    assert isinstance(log[1], ValueError)


@pytest.mark.asyncio
async def test_on_exception_max_tries() -> None:
    @backoff.on_exception(backoff.expo, KeyError, jitter=None, max_tries=3)
    async def keyerror_then_true(log, n, foo=None):
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log: list[Exception] = []
    with pytest.raises(KeyError):
        await keyerror_then_true(log, 10, foo="bar")

    assert len(log) == 3


@pytest.mark.asyncio
async def test_on_exception_max_tries_callable() -> None:
    @backoff.on_exception(backoff.expo, KeyError, jitter=None, max_tries=lambda: 3)
    async def keyerror_then_true(log, n, foo=None):
        if len(log) == n:
            return True
        e = KeyError()
        log.append(e)
        raise e

    log: list[Exception] = []
    with pytest.raises(KeyError):
        await keyerror_then_true(log, 10, foo="bar")

    assert len(log) == 3


@pytest.mark.asyncio
async def test_on_exception_constant_iterable(appender: EventAppender) -> None:
    @backoff.on_exception(
        backoff.constant,
        KeyError,
        interval=(1, 2, 3),
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
    )
    async def endless_exceptions():
        raise KeyError("foo")

    with pytest.raises(KeyError):
        await endless_exceptions()

    assert appender.counts() == {
        "backoff": 3,
        "giveup": 1,
        "success": 0,
        "try": 4,
    }


@pytest.mark.asyncio
async def test_on_exception_success_random_jitter(appender: EventAppender) -> None:
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
    async def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(appender.events["backoff"]) < 2:
            raise ValueError("catch me")

    await succeeder(1, 2, 3, foo=1, bar=2)

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


@pytest.mark.asyncio
async def test_on_exception_success_full_jitter(appender: EventAppender) -> None:
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
    async def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(appender.events["backoff"]) < 2:
            raise ValueError("catch me")

    await succeeder(1, 2, 3, foo=1, bar=2)

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


@pytest.mark.asyncio
async def test_on_exception_success(appender: EventAppender) -> None:
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
    async def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(appender.events["backoff"]) < 2:
            raise ValueError("catch me")

    await succeeder(1, 2, 3, foo=1, bar=2)

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


@pytest.mark.asyncio
async def test_on_exception_on_try_runs_before_attempt() -> None:
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
    async def fails():
        calls.append("call")
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        await fails()

    assert calls == [
        ("try", 1, 0),
        "call",
        ("try", 2, IsFloat(gt=0)),
        "call",
        ("try", 3, IsFloat(gt=0)),
        "call",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_on_giveup", [True, False])
async def test_on_exception_giveup(
    raise_on_giveup: bool,
    appender: EventAppender,
) -> None:
    @backoff.on_exception(
        backoff.constant,
        ValueError,
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_success=appender.on_event("success"),
        on_try=appender.on_event("try"),
        raise_on_giveup=raise_on_giveup,
        max_tries=3,
        jitter=None,
        interval=0,
    )
    @_save_target
    async def exceptor(*args, **kwargs):
        raise ValueError("catch me")

    if raise_on_giveup:
        with pytest.raises(ValueError, match="catch me"):
            await exceptor(1, 2, 3, foo=1, bar=2)
    else:
        await exceptor(1, 2, 3, foo=1, bar=2)

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


@pytest.mark.asyncio
async def test_on_exception_giveup_predicate() -> None:
    def on_baz(e):
        return str(e) == "baz"

    vals = ["baz", "bar", "foo"]

    @backoff.on_exception(backoff.constant, ValueError, giveup=on_baz)
    async def foo_bar_baz():
        raise ValueError(vals.pop())

    with pytest.raises(ValueError, match=r"(baz|bar|foo)"):
        await foo_bar_baz()

    assert not vals


@pytest.mark.asyncio
async def test_on_exception_giveup_coro() -> None:
    async def on_baz(e: Exception) -> bool:
        return str(e) == "baz"

    vals = ["baz", "bar", "foo"]

    @backoff.on_exception(backoff.constant, ValueError, giveup=on_baz)
    async def foo_bar_baz():
        raise ValueError(vals.pop())

    with pytest.raises(ValueError, match=r"(baz|bar|foo)"):
        await foo_bar_baz()

    assert not vals


@pytest.mark.asyncio
async def test_on_predicate_success(appender: EventAppender) -> None:
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
    async def success(*args, **kwargs):
        # succeed after we've backed off twice
        return len(appender.events["backoff"]) == 2

    await success(1, 2, 3, foo=1, bar=2)

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


@pytest.mark.asyncio
async def test_on_predicate_on_try_runs_before_attempt() -> None:
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
    async def falsey():
        calls.append("call")
        return False

    await falsey()

    assert calls == [
        ("try", 1, 0),
        "call",
        ("try", 2, IsFloat(gt=0)),
        "call",
        ("try", 3, IsFloat(gt=0)),
        "call",
    ]


@pytest.mark.asyncio
async def test_on_predicate_giveup(appender: EventAppender) -> None:
    @backoff.on_predicate(
        backoff.constant,
        on_success=appender.on_event("success"),
        on_backoff=appender.on_event("backoff"),
        on_giveup=appender.on_event("giveup"),
        on_try=appender.on_event("try"),
        max_tries=3,
        jitter=None,
        interval=0,
    )
    @_save_target
    async def emptiness(*args, **kwargs):
        pass

    await emptiness(1, 2, 3, foo=1, bar=2)

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


@pytest.mark.asyncio
async def test_on_predicate_iterable_handlers() -> None:
    appenders = [EventAppender() for _ in range(3)]

    @backoff.on_predicate(
        backoff.constant,
        on_backoff=(a.on_event("backoff") for a in appenders),
        on_giveup=(a.on_event("giveup") for a in appenders),
        on_success=(a.on_event("success") for a in appenders),
        on_try=(a.on_event("try") for a in appenders),
        max_tries=3,
        jitter=None,
        interval=0,
    )
    @_save_target
    async def emptiness(*args, **kwargs):
        pass

    await emptiness(1, 2, 3, foo=1, bar=2)

    for i in range(3):
        assert appenders[i].counts() == {
            "backoff": 2,
            "giveup": 1,
            "success": 0,
            "try": 3,
        }

        details = appenders[i].events["giveup"][0]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": emptiness._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": 3,
            "value": None,
            "elapsed": IsFloat(gt=0),
        }


@pytest.mark.asyncio
async def test_on_predicate_constant_iterable(appender: EventAppender) -> None:
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
    async def falsey():
        return False

    assert not await falsey()
    assert appender.counts() == {
        "backoff": len(waits),
        "giveup": 1,
        "success": 0,
        "try": len(waits) + 1,
    }

    for i, wait in enumerate(waits):
        assert appender.events["backoff"][i]["wait"] == wait


@pytest.mark.asyncio
async def test_on_exception_jitter(appender: EventAppender) -> None:
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
    async def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(appender.events["backoff"]) < 2:
            raise ValueError("catch me")

    await succeeder(1, 2, 3, foo=1, bar=2)

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


@pytest.mark.asyncio
async def test_on_predicate_jitter(appender: EventAppender) -> None:
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
    async def success(*args, **kwargs):
        # succeed after we've backed off twice
        return len(appender.events["backoff"]) == 2

    await success(1, 2, 3, foo=1, bar=2)

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


@pytest.mark.asyncio
async def test_on_exception_callable_max_tries() -> None:
    def lookup_max_tries():
        return 3

    log = []

    @backoff.on_exception(backoff.constant, ValueError, max_tries=lookup_max_tries)
    async def exceptor():
        log.append(True)
        raise ValueError("aah")

    with pytest.raises(ValueError, match="aah"):
        await exceptor()

    assert len(log) == 3


@pytest.mark.asyncio
async def test_on_exception_callable_max_tries_reads_every_time() -> None:

    lookups = []

    def lookup_max_tries():
        lookups.append(True)
        return 3

    @backoff.on_exception(backoff.constant, ValueError, max_tries=lookup_max_tries)
    async def exceptor():
        raise ValueError("aah")

    with pytest.raises(ValueError, match="aah"):
        await exceptor()

    with pytest.raises(ValueError, match="aah"):
        await exceptor()

    assert len(lookups) == 2


@pytest.mark.asyncio
async def test_on_exception_callable_gen_kwargs() -> None:
    def lookup_foo():
        return "foo"

    def wait_gen(foo=None, bar=None) -> Generator[float, None, None]:
        assert foo == "foo"
        assert bar == "bar"

        while True:
            yield 0

    @backoff.on_exception(wait_gen, ValueError, max_tries=2, foo=lookup_foo, bar="bar")
    async def exceptor():
        raise ValueError("aah")

    with pytest.raises(ValueError, match="aah"):
        await exceptor()


@pytest.mark.asyncio
async def test_on_exception_coro_cancelling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", asyncio_sleep)
    sleep_started_event = asyncio.Event()

    @backoff.on_predicate(backoff.expo)
    async def coro():
        sleep_started_event.set()

        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return True

        return False

    task = asyncio.create_task(coro())

    await sleep_started_event.wait()

    task.cancel()

    assert await task


@pytest.mark.asyncio
async def test_max_time(monkeypatch: pytest.MonkeyPatch):
    elapsed: float = 0

    async def patch_sleep(n: float):
        nonlocal elapsed
        elapsed += n

    def monotonic():
        return elapsed

    monkeypatch.setattr("asyncio.sleep", patch_sleep)
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
        async def on_exception():
            await patch_sleep(function_runtime)  # ruff: ignore[function-uses-loop-variable]
            raise RuntimeError

        with contextlib.suppress(BaseException):
            await on_exception()

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
        async def on_predicate():
            await patch_sleep(function_runtime)  # ruff: ignore[function-uses-loop-variable]

        await on_predicate()
        assert elapsed <= max_time + function_runtime + 1e-9

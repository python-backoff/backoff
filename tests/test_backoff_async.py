from __future__ import annotations

import asyncio
import contextlib
import itertools
import time
from typing import TYPE_CHECKING

import pytest
from dirty_equals import IsFloat, IsInstance

import backoff
from tests.common import _log_hdlrs, _save_target

if TYPE_CHECKING:
    from collections.abc import Generator

    from backoff._typing import Details


async def _await_none(x):
    return None


@pytest.mark.asyncio
async def test_on_predicate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_predicate_max_tries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_predicate_max_tries_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_exception_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_exception_max_tries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_exception_max_tries_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_exception_constant_iterable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

    backoffs: list[Details] = []
    giveups: list[Details] = []
    successes: list[Details] = []

    @backoff.on_exception(
        backoff.constant,
        KeyError,
        interval=(1, 2, 3),
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        on_success=successes.append,
    )
    async def endless_exceptions():
        raise KeyError("foo")

    with pytest.raises(KeyError):
        await endless_exceptions()

    assert len(backoffs) == 3
    assert len(giveups) == 1
    assert len(successes) == 0


@pytest.mark.asyncio
async def test_on_exception_success_random_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(
        backoff.expo,
        Exception,
        on_success=log_success,
        on_backoff=log_backoff,
        on_giveup=log_giveup,
        jitter=backoff.random_jitter,
        factor=0.5,
    )
    @_save_target
    async def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(log["backoff"]) < 2:
            raise ValueError("catch me")

    await succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log["success"]) == 1
    assert len(log["backoff"]) == 2
    assert len(log["giveup"]) == 0

    for i in range(2):
        details = log["backoff"][i]
        assert details["wait"] >= 0.5 * 2**i


@pytest.mark.asyncio
async def test_on_exception_success_full_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(
        backoff.expo,
        Exception,
        on_success=log_success,
        on_backoff=log_backoff,
        on_giveup=log_giveup,
        jitter=backoff.full_jitter,
        factor=0.5,
    )
    @_save_target
    async def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(log["backoff"]) < 2:
            raise ValueError("catch me")

    await succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log["success"]) == 1
    assert len(log["backoff"]) == 2
    assert len(log["giveup"]) == 0

    for i in range(2):
        details = log["backoff"][i]
        assert details["wait"] <= 0.5 * 2**i


@pytest.mark.asyncio
async def test_on_exception_success() -> None:
    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(
        backoff.constant,
        Exception,
        on_success=log_success,
        on_backoff=log_backoff,
        on_giveup=log_giveup,
        jitter=None,
        interval=0,
    )
    @_save_target
    async def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(log["backoff"]) < 2:
            raise ValueError("catch me")

    await succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log["success"]) == 1
    assert len(log["backoff"]) == 2
    assert len(log["giveup"]) == 0

    for i in range(2):
        details = log["backoff"][i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
            "exception": IsInstance(ValueError),
        }

    details = log["success"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "elapsed": IsFloat(gt=0),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_on_giveup", [True, False])
async def test_on_exception_giveup(raise_on_giveup: bool) -> None:
    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(
        backoff.constant,
        ValueError,
        on_success=log_success,
        on_backoff=log_backoff,
        on_giveup=log_giveup,
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
    assert len(log["success"]) == 0
    assert len(log["backoff"]) == 2
    assert len(log["giveup"]) == 1

    details = log["giveup"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": exceptor._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "elapsed": IsFloat(gt=0),
        "exception": IsInstance(ValueError),
    }


@pytest.mark.asyncio
async def test_on_exception_giveup_predicate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_exception_giveup_coro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_predicate_success() -> None:
    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_predicate(
        backoff.constant,
        on_success=log_success,
        on_backoff=log_backoff,
        on_giveup=log_giveup,
        jitter=None,
        interval=0,
    )
    @_save_target
    async def success(*args, **kwargs):
        # succeed after we've backed off twice
        return len(log["backoff"]) == 2

    await success(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log["success"]) == 1
    assert len(log["backoff"]) == 2
    assert len(log["giveup"]) == 0

    for i in range(2):
        details = log["backoff"][i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "value": False,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
        }

    details = log["success"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "value": True,
        "elapsed": IsFloat(gt=0),
    }


@pytest.mark.asyncio
async def test_on_predicate_giveup() -> None:
    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_predicate(
        backoff.constant,
        on_success=log_success,
        on_backoff=log_backoff,
        on_giveup=log_giveup,
        max_tries=3,
        jitter=None,
        interval=0,
    )
    @_save_target
    async def emptiness(*args, **kwargs):
        pass

    await emptiness(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice and giving up once
    assert len(log["success"]) == 0
    assert len(log["backoff"]) == 2
    assert len(log["giveup"]) == 1

    details = log["giveup"][0]
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
    hdlrs = [_log_hdlrs() for _ in range(3)]

    @backoff.on_predicate(
        backoff.constant,
        on_success=(h[1] for h in hdlrs),
        on_backoff=(h[2] for h in hdlrs),
        on_giveup=(h[3] for h in hdlrs),
        max_tries=3,
        jitter=None,
        interval=0,
    )
    @_save_target
    async def emptiness(*args, **kwargs):
        pass

    await emptiness(1, 2, 3, foo=1, bar=2)

    for i in range(3):
        assert len(hdlrs[i][0]["success"]) == 0
        assert len(hdlrs[i][0]["backoff"]) == 2
        assert len(hdlrs[i][0]["giveup"]) == 1

        details = hdlrs[i][0]["giveup"][0]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": emptiness._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": 3,
            "value": None,
            "elapsed": IsFloat(gt=0),
        }


@pytest.mark.asyncio
async def test_on_predicate_constant_iterable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
    async def falsey():
        return False

    assert not await falsey()

    assert len(backoffs) == len(waits)
    for i, wait in enumerate(waits):
        assert backoffs[i]["wait"] == wait

    assert len(giveups) == 1
    assert len(successes) == 0


# To maintain backward compatibility,
# on_predicate should support 0-argument jitter function.
@pytest.mark.asyncio
async def test_on_exception_success_0_arg_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_exception(
        backoff.constant,
        Exception,
        on_success=log_success,
        on_backoff=log_backoff,
        on_giveup=log_giveup,
        jitter=lambda: 0.0,  # type:ignore[arg-type,misc] # ty:ignore[invalid-argument-type]
        interval=0,
    )
    @_save_target
    async def succeeder(*args, **kwargs):
        # succeed after we've backed off twice
        if len(log["backoff"]) < 2:
            raise ValueError("catch me")

    with pytest.deprecated_call(
        match="Nullary jitter function signature is deprecated",
    ):
        await succeeder(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log["success"]) == 1
    assert len(log["backoff"]) == 2
    assert len(log["giveup"]) == 0

    for i in range(2):
        details = log["backoff"][i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
            "exception": IsInstance(ValueError),
        }

    details = log["success"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": succeeder._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "elapsed": IsFloat(gt=0),
    }


# To maintain backward compatibility,
# on_predicate should support 0-argument jitter function.
@pytest.mark.asyncio
async def test_on_predicate_success_0_arg_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

    log, log_success, log_backoff, log_giveup = _log_hdlrs()

    @backoff.on_predicate(
        backoff.constant,
        on_success=log_success,
        on_backoff=log_backoff,
        on_giveup=log_giveup,
        jitter=lambda: 0.0,  # type:ignore[arg-type,misc] # ty:ignore[invalid-argument-type]
        interval=0,
    )
    @_save_target
    async def success(*args, **kwargs):
        # succeed after we've backed off twice
        return len(log["backoff"]) == 2

    with pytest.deprecated_call(
        match="Nullary jitter function signature is deprecated",
    ):
        await success(1, 2, 3, foo=1, bar=2)

    # we try 3 times, backing off twice before succeeding
    assert len(log["success"]) == 1
    assert len(log["backoff"]) == 2
    assert len(log["giveup"]) == 0

    for i in range(2):
        details = log["backoff"][i]
        assert details == {
            "args": (1, 2, 3),
            "kwargs": {"foo": 1, "bar": 2},
            "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
            "tries": i + 1,
            "value": False,
            "wait": 0,
            "elapsed": IsFloat(gt=0),
        }

    details = log["success"][0]
    assert details == {
        "args": (1, 2, 3),
        "kwargs": {"foo": 1, "bar": 2},
        "target": success._target,  # type:ignore[attr-defined] # ty:ignore[unresolved-attribute]
        "tries": 3,
        "value": True,
        "elapsed": IsFloat(gt=0),
    }


@pytest.mark.asyncio
async def test_on_exception_callable_max_tries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_exception_callable_max_tries_reads_every_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("asyncio.sleep", _await_none)

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
async def test_on_exception_coro_cancelling() -> None:
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
async def test_max_time(monkeypatch):
    start = time.monotonic()
    elapsed: float = 0

    async def patch_sleep(n: float):
        nonlocal elapsed
        elapsed += n

    def monotonic():
        nonlocal start, elapsed
        return start + elapsed

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

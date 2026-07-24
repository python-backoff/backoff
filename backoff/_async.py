from __future__ import annotations

import asyncio
import functools
import inspect
import time
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from backoff._common import _init_wait_gen, _maybe_call, _next_wait

if TYPE_CHECKING:
    import sys
    from collections.abc import Coroutine, Iterable

    from backoff._typing import (
        Details,
        _BaseDetails,
        _CallDetails,
        _Handler,
        _Jitterer,
        _MaybeCallable,
        _MaybeSequence,
        _Predicate,
        _WaitGenerator,
    )

    if sys.version_info >= (3, 10):
        from typing import ParamSpec
    else:
        from typing_extensions import ParamSpec

    if sys.version_info >= (3, 11):
        from typing import Unpack
    else:
        from typing_extensions import Unpack

    T = TypeVar("T")
    P = ParamSpec("P")

_AsyncHandler = Callable[["Details"], "Coroutine[Any, Any, None]"]


def _ensure_coroutine(
    coro_or_func: Callable[..., Any],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    if inspect.iscoroutinefunction(coro_or_func):
        return coro_or_func

    @functools.wraps(coro_or_func)
    async def f(*args: Any, **kwargs: Any) -> Any:  # ruff:ignore[unused-async]
        return coro_or_func(*args, **kwargs)

    return f


def _ensure_coroutines(
    coros_or_funcs: Iterable[Callable[..., Any]],
) -> list[Callable[..., Coroutine[Any, Any, Any]]]:
    return [_ensure_coroutine(f) for f in coros_or_funcs]


async def _call_handlers(
    handlers: Iterable[_AsyncHandler],
    *,
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    tries: int,
    elapsed: float,
    **extra: Unpack[_CallDetails],
) -> None:
    details: Details = {
        "target": target,
        "args": args,
        "kwargs": kwargs,
        "tries": tries,
        "elapsed": elapsed,
    }
    # pyrefly: ignore [no-matching-overload]
    details.update(extra)
    for handler in handlers:
        await handler(details)


def retry_predicate(
    target: Callable[P, T],
    wait_gen: _WaitGenerator,
    predicate: _Predicate[T],
    *,
    max_tries: _MaybeCallable[int] | None,
    max_time: _MaybeCallable[float] | None,
    jitter: _Jitterer | None,
    on_success: Iterable[_Handler],
    on_backoff: Iterable[_Handler],
    on_giveup: Iterable[_Handler],
    wait_gen_kwargs: dict[str, Any],
) -> Callable[P, T]:
    on_success = _ensure_coroutines(on_success)
    on_backoff = _ensure_coroutines(on_backoff)
    on_giveup = _ensure_coroutines(on_giveup)

    # Easy to implement, please report if you need this.
    assert not inspect.iscoroutinefunction(max_tries)
    assert not inspect.iscoroutinefunction(jitter)

    assert inspect.iscoroutinefunction(target)

    @functools.wraps(target)
    async def retry(*args: P.args, **kwargs: P.kwargs) -> T:
        # update variables from outer function args
        max_tries_value: int | None = _maybe_call(max_tries)
        max_time_value: float | None = _maybe_call(max_time)

        tries = 0
        start = time.monotonic()
        wait = _init_wait_gen(wait_gen, wait_gen_kwargs)
        while True:
            tries += 1
            elapsed = time.monotonic() - start
            details: _BaseDetails = {
                "target": target,
                "args": args,
                "kwargs": kwargs,
                "tries": tries,
                "elapsed": elapsed,
            }

            ret = await target(*args, **kwargs)
            if predicate(ret):
                max_tries_exceeded = tries == max_tries_value
                max_time_exceeded = (
                    max_time_value is not None and elapsed >= max_time_value
                )

                if max_tries_exceeded or max_time_exceeded:
                    await _call_handlers(on_giveup, **details, value=ret)
                    break

                try:
                    seconds = _next_wait(wait, ret, jitter, elapsed, max_time_value)
                except StopIteration:
                    await _call_handlers(on_giveup, **details, value=ret)
                    break

                await _call_handlers(on_backoff, **details, value=ret, wait=seconds)

                # Note: there is no convenient way to pass explicit event
                # loop to decorator, so here we assume that either default
                # thread event loop is set and correct (it mostly is
                # by default), or Python >= 3.5.3 or Python >= 3.6 is used
                # where loop.get_event_loop() in coroutine guaranteed to
                # return correct value.
                # See for details:
                #   <https://groups.google.com/forum/#!topic/python-tulip/yF9C-rFpiKk>
                #   <https://bugs.python.org/issue28613>
                await asyncio.sleep(seconds)
                continue
            await _call_handlers(on_success, **details, value=ret)
            break

        return ret

    return retry  # type: ignore[return-value] # ty:ignore[invalid-return-type]


def retry_exception(
    target: Callable[P, T],
    wait_gen: _WaitGenerator,
    exception: _MaybeSequence[type[Exception]],
    *,
    max_tries: _MaybeCallable[int] | None,
    max_time: _MaybeCallable[float] | None,
    jitter: _Jitterer | None,
    giveup: _Predicate[Exception],
    on_success: Iterable[_Handler],
    on_backoff: Iterable[_Handler],
    on_giveup: Iterable[_Handler],
    raise_on_giveup: bool,
    wait_gen_kwargs: dict[str, Any],
) -> Callable[P, T]:
    on_success = _ensure_coroutines(on_success)
    on_backoff = _ensure_coroutines(on_backoff)
    on_giveup = _ensure_coroutines(on_giveup)
    giveup = _ensure_coroutine(giveup)

    # Easy to implement, please report if you need this.
    assert not inspect.iscoroutinefunction(max_tries)
    assert not inspect.iscoroutinefunction(jitter)

    @functools.wraps(target)
    async def retry(
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        max_tries_value: int | None = _maybe_call(max_tries)
        max_time_value: float | None = _maybe_call(max_time)

        tries = 0
        start = time.monotonic()
        wait = _init_wait_gen(wait_gen, wait_gen_kwargs)
        while True:
            tries += 1
            elapsed = time.monotonic() - start
            details: _BaseDetails = {
                "target": target,
                "args": args,
                "kwargs": kwargs,
                "tries": tries,
                "elapsed": elapsed,
            }

            try:
                ret = await target(*args, **kwargs)  # type: ignore[misc] # ty:ignore[invalid-await]
            except exception as e:  # type: ignore[misc] # ty:ignore[invalid-exception-caught]
                giveup_result = await giveup(e)
                max_tries_exceeded = tries == max_tries_value
                max_time_exceeded = (
                    max_time_value is not None and elapsed >= max_time_value
                )

                if giveup_result or max_tries_exceeded or max_time_exceeded:
                    await _call_handlers(on_giveup, **details, exception=e)
                    if raise_on_giveup:
                        raise
                    return None  # type: ignore[return-value] # ty:ignore[invalid-return-type]

                try:
                    seconds = _next_wait(wait, e, jitter, elapsed, max_time_value)
                except StopIteration:
                    await _call_handlers(on_giveup, **details, exception=e)
                    raise e from None

                await _call_handlers(on_backoff, **details, wait=seconds, exception=e)

                # Note: there is no convenient way to pass explicit event
                # loop to decorator, so here we assume that either default
                # thread event loop is set and correct (it mostly is
                # by default), or Python >= 3.5.3 or Python >= 3.6 is used
                # where loop.get_event_loop() in coroutine guaranteed to
                # return correct value.
                # See for details:
                #   <https://groups.google.com/forum/#!topic/python-tulip/yF9C-rFpiKk>
                #   <https://bugs.python.org/issue28613>
                await asyncio.sleep(seconds)
            else:
                await _call_handlers(on_success, **details)

                return ret

    return retry  # type: ignore[return-value] # ty:ignore[invalid-return-type]

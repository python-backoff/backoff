from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from backoff._common import _Attempt, _RetryState

if TYPE_CHECKING:
    import sys
    from collections.abc import AsyncGenerator, Coroutine, Iterable
    from typing import ParamSpec

    from backoff._typing import (
        ContextDetails,
        Details,
        _BaseDetails,
        _CallDetails,
        _ContextHandler,
        _Handler,
        _Jitterer,
        _MaybeCallable,
        _MaybeTuple,
        _Predicate,
        _WaitGenerator,
    )

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
    target: Callable[P, Coroutine[object, object, T]],
    wait_gen: _WaitGenerator,
    predicate: _Predicate[T],
    *,
    max_tries: _MaybeCallable[int] | None,
    max_time: _MaybeCallable[float] | None,
    jitter: _Jitterer | None,
    on_try: Iterable[_Handler],
    on_success: Iterable[_Handler],
    on_backoff: Iterable[_Handler],
    on_giveup: Iterable[_Handler],
    wait_gen_kwargs: dict[str, Any],
) -> Callable[P, Coroutine[object, object, T]]:
    on_try = _ensure_coroutines(on_try)
    on_success = _ensure_coroutines(on_success)
    on_backoff = _ensure_coroutines(on_backoff)
    on_giveup = _ensure_coroutines(on_giveup)

    # Easy to implement, please report if you need this.
    assert not inspect.iscoroutinefunction(max_tries)
    assert not inspect.iscoroutinefunction(jitter)

    assert inspect.iscoroutinefunction(target)

    @functools.wraps(target)
    async def retry(*args: P.args, **kwargs: P.kwargs) -> T:
        state = _RetryState(
            wait_gen,
            wait_gen_kwargs,
            max_tries=max_tries,
            max_time=max_time,
        )
        while True:
            state.start_attempt()
            details: _BaseDetails = {
                "target": target,
                "args": args,
                "kwargs": kwargs,
                "tries": state.tries,
                "elapsed": state.elapsed,
            }
            await _call_handlers(on_try, **details)
            ret = await target(*args, **kwargs)
            details["elapsed"] = state.record_elapsed()

            if predicate(ret):
                if state.exhausted():
                    await _call_handlers(on_giveup, **details, value=ret)
                    break

                try:
                    seconds = state.next_wait(ret, jitter)
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

    return retry


def _adapt_context_handlers(
    handlers: Iterable[_AsyncHandler],
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> list[_ContextHandler]:
    async def adapted(details: ContextDetails) -> None:
        full_details: Details = {
            "target": target,
            "args": args,
            "kwargs": kwargs,
            **details,
        }
        for hdlr in handlers:
            await hdlr(full_details)

    return [adapted]


def retry_exception(
    target: Callable[P, Coroutine[object, object, T]],
    wait_gen: _WaitGenerator,
    exception: _MaybeTuple[type[Exception]],
    *,
    max_tries: _MaybeCallable[int] | None,
    max_time: _MaybeCallable[float] | None,
    jitter: _Jitterer | None,
    giveup: _Predicate[Exception],
    on_try: Iterable[_Handler],
    on_success: Iterable[_Handler],
    on_backoff: Iterable[_Handler],
    on_giveup: Iterable[_Handler],
    raise_on_giveup: bool,
    wait_gen_kwargs: dict[str, Any],
) -> Callable[P, Coroutine[object, object, T]]:
    on_try = _ensure_coroutines(on_try)
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
        ret: T = None  # type: ignore[assignment] # ty:ignore[invalid-assignment]

        async for attempt in aretry_context(
            exception,
            wait_gen,
            max_tries=max_tries,
            max_time=max_time,
            jitter=jitter,
            giveup=giveup,
            on_try=_adapt_context_handlers(on_try, target, args, kwargs),
            on_success=_adapt_context_handlers(on_success, target, args, kwargs),
            on_backoff=_adapt_context_handlers(on_backoff, target, args, kwargs),
            on_giveup=_adapt_context_handlers(on_giveup, target, args, kwargs),
            raise_on_giveup=raise_on_giveup,
            wait_gen_kwargs=wait_gen_kwargs,
        ):
            with attempt:
                ret = await target(*args, **kwargs)

        return ret

    return retry


async def _dispatch_handlers(
    handlers: Iterable[_ContextHandler], **details: Any
) -> None:
    for hdlr in _ensure_coroutines(handlers):
        await hdlr(details)


async def aretry_context(
    exception: _MaybeTuple[type[Exception]],
    wait_gen: _WaitGenerator,
    *,
    max_tries: _MaybeCallable[int] | None,
    max_time: _MaybeCallable[float] | None,
    jitter: _Jitterer | None,
    giveup: _Predicate[BaseException],
    on_try: Iterable[_ContextHandler],
    on_success: Iterable[_ContextHandler],
    on_backoff: Iterable[_ContextHandler],
    on_giveup: Iterable[_ContextHandler],
    raise_on_giveup: bool,
    wait_gen_kwargs: dict[str, Any],
) -> AsyncGenerator[_Attempt, None]:
    giveup = _ensure_coroutine(giveup)

    state = _RetryState(
        wait_gen,
        wait_gen_kwargs,
        max_tries=max_tries,
        max_time=max_time,
    )
    while True:
        state.start_attempt()
        attempt = _Attempt(exception)
        await _dispatch_handlers(
            handlers=on_try,
            tries=state.tries,
            elapsed=state.elapsed,
        )
        yield attempt
        elapsed = state.record_elapsed()

        exc = attempt.exception
        if exc is None:
            await _dispatch_handlers(on_success, tries=state.tries, elapsed=elapsed)
            return

        if await giveup(exc) or state.exhausted():
            await _dispatch_handlers(
                on_giveup,
                tries=state.tries,
                elapsed=elapsed,
                exception=exc,
            )
            if raise_on_giveup:
                raise exc
            return

        try:
            seconds = state.next_wait(exc, jitter)
        except StopIteration:
            await _dispatch_handlers(
                on_giveup,
                tries=state.tries,
                elapsed=elapsed,
                exception=exc,
            )
            raise exc from None

        await _dispatch_handlers(
            on_backoff,
            tries=state.tries,
            elapsed=elapsed,
            wait=seconds,
            exception=exc,
        )

        await asyncio.sleep(seconds)

from __future__ import annotations

import functools
import time
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from backoff._common import _Attempt, _dispatch_handlers, _RetryState

if TYPE_CHECKING:
    import sys
    from collections.abc import Generator, Iterable

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


def _call_handlers(
    hdlrs: Iterable[_Handler],
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
    for hdlr in hdlrs:
        hdlr(details)


def retry_predicate(
    target: Callable[P, T],
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
) -> Callable[P, T]:
    @functools.wraps(target)
    def retry(*args: P.args, **kwargs: P.kwargs) -> T:
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
            _call_handlers(on_try, **details)
            ret = target(*args, **kwargs)
            details["elapsed"] = state.record_elapsed()

            if predicate(ret):
                if state.exhausted():
                    _call_handlers(on_giveup, **details, value=ret)
                    break

                try:
                    seconds = state.next_wait(ret, jitter)
                except StopIteration:
                    _call_handlers(on_giveup, **details, value=ret)
                    break

                _call_handlers(on_backoff, **details, value=ret, wait=seconds)

                time.sleep(seconds)
                continue
            _call_handlers(on_success, **details, value=ret)
            break

        return ret

    return retry


def _adapt_context_handlers(
    handlers: Iterable[_Handler],
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> list[_ContextHandler]:
    def adapted(details: ContextDetails) -> None:
        full_details: Details = {
            "target": target,
            "args": args,
            "kwargs": kwargs,
            **details,
        }
        for hdlr in handlers:
            hdlr(full_details)

    return [adapted]


def retry_exception(
    target: Callable[P, T],
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
) -> Callable[P, T]:
    @functools.wraps(target)
    def retry(*args: P.args, **kwargs: P.kwargs) -> T:
        ret: T = None  # type: ignore[assignment] # ty:ignore[invalid-assignment]

        for attempt in retry_context(
            exception,
            wait_gen,
            max_tries=max_tries,
            max_time=max_time,
            jitter=jitter,
            giveup=giveup,  # type: ignore[arg-type] # ty:ignore[invalid-argument-type]
            on_try=_adapt_context_handlers(on_try, target, args, kwargs),
            on_success=_adapt_context_handlers(on_success, target, args, kwargs),
            on_backoff=_adapt_context_handlers(on_backoff, target, args, kwargs),
            on_giveup=_adapt_context_handlers(on_giveup, target, args, kwargs),
            raise_on_giveup=raise_on_giveup,
            wait_gen_kwargs=wait_gen_kwargs,
        ):
            with attempt:
                ret = target(*args, **kwargs)

        return ret

    return retry


def retry_context(
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
) -> Generator[_Attempt, None, None]:
    state = _RetryState(
        wait_gen,
        wait_gen_kwargs,
        max_tries=max_tries,
        max_time=max_time,
    )
    while True:
        state.start_attempt()
        attempt = _Attempt(exception)
        _dispatch_handlers(handlers=on_try, tries=state.tries, elapsed=state.elapsed)
        yield attempt
        elapsed = state.record_elapsed()

        exc = attempt.exception
        if exc is None:
            _dispatch_handlers(on_success, tries=state.tries, elapsed=elapsed)
            return

        if giveup(exc) or state.exhausted():
            _dispatch_handlers(
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
            _dispatch_handlers(
                on_giveup,
                tries=state.tries,
                elapsed=elapsed,
                exception=exc,
            )
            raise exc from None

        _dispatch_handlers(
            on_backoff,
            tries=state.tries,
            elapsed=elapsed,
            wait=seconds,
            exception=exc,
        )

        time.sleep(seconds)

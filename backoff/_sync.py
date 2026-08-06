from __future__ import annotations

import functools
import time
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from backoff._common import _Attempt, _dispatch_handlers, _RetryState

if TYPE_CHECKING:
    import sys
    from collections.abc import Generator, Iterable

    from backoff._typing import (
        Details,
        _BaseDetails,
        _CallDetails,
        _ContextHandler,
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
            ret = target(*args, **kwargs)
            details: _BaseDetails = {
                "target": target,
                "args": args,
                "kwargs": kwargs,
                "tries": state.tries,
                "elapsed": state.record_elapsed(),
            }

            if predicate(ret):
                if state.exhausted():
                    _call_handlers(on_giveup, **details, value=ret)
                    break

                try:
                    seconds = state.next_wait(ret, jitter)
                except StopIteration:
                    _call_handlers(on_giveup, **details)
                    break

                _call_handlers(on_backoff, **details, value=ret, wait=seconds)

                time.sleep(seconds)
                continue
            _call_handlers(on_success, **details, value=ret)
            break

        return ret

    return retry


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
    @functools.wraps(target)
    def retry(*args: P.args, **kwargs: P.kwargs) -> T:  # type: ignore[return]  # ty:ignore[invalid-return-type]
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
                "elapsed": 0,
            }

            try:
                ret = target(*args, **kwargs)
            except exception as e:  # type: ignore[misc] # ty:ignore[invalid-exception-caught]
                details["elapsed"] = state.record_elapsed()

                if giveup(e) or state.exhausted():
                    _call_handlers(on_giveup, **details, exception=e)
                    if raise_on_giveup:
                        raise
                    break

                try:
                    seconds = state.next_wait(e, jitter)
                except StopIteration:
                    _call_handlers(on_giveup, **details, exception=e)
                    raise e from None

                _call_handlers(on_backoff, **details, wait=seconds, exception=e)

                time.sleep(seconds)
            else:
                details["elapsed"] = state.record_elapsed()
                _call_handlers(on_success, **details)

                return ret

    return retry


def retry_context(
    exception: _MaybeSequence[type[Exception]],
    wait_gen: _WaitGenerator,
    *,
    max_tries: _MaybeCallable[int] | None,
    max_time: _MaybeCallable[float] | None,
    jitter: _Jitterer | None,
    giveup: _Predicate[BaseException],
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
        attempt = _Attempt(exception)  # type: ignore[arg-type] # ty:ignore[invalid-argument-type]
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

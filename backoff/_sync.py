from __future__ import annotations

import functools
import time
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from backoff._common import _init_wait_gen, _maybe_call, _next_wait

if TYPE_CHECKING:
    import sys
    from collections.abc import Iterable

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

            ret = target(*args, **kwargs)
            if predicate(ret):
                max_tries_exceeded = tries == max_tries_value
                max_time_exceeded = (
                    max_time_value is not None and elapsed >= max_time_value
                )

                if max_tries_exceeded or max_time_exceeded:
                    _call_handlers(on_giveup, **details, value=ret)
                    break

                try:
                    seconds = _next_wait(wait, ret, jitter, elapsed, max_time_value)
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
                ret = target(*args, **kwargs)
            except exception as e:  # type: ignore[misc] # ty:ignore[invalid-exception-caught]
                max_tries_exceeded = tries == max_tries_value
                max_time_exceeded = (
                    max_time_value is not None and elapsed >= max_time_value
                )

                if giveup(e) or max_tries_exceeded or max_time_exceeded:
                    _call_handlers(on_giveup, **details, exception=e)
                    if raise_on_giveup:
                        raise
                    break

                try:
                    seconds = _next_wait(wait, e, jitter, elapsed, max_time_value)
                except StopIteration:
                    _call_handlers(on_giveup, **details, exception=e)
                    raise e from None

                _call_handlers(on_backoff, **details, wait=seconds, exception=e)

                time.sleep(seconds)
            else:
                _call_handlers(on_success, **details)

                return ret

    return retry

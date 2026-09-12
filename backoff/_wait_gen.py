from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable

    from backoff._typing import _WaitGenerator


def expo(
    base: float = 2,
    factor: float = 1,
    max_value: float | None = None,
) -> Generator[float, Any, None]:
    """Generator for exponential decay.

    Args:
        base: The mathematical base of the exponentiation operation
        factor: Factor to multiply the exponentiation by.
        max_value: The maximum value to yield. Once the value in the
             true exponential sequence exceeds this, the value
             of max_value will forever after be yielded.
    """
    # Advance past initial .send() call
    yield 0

    a = factor
    while max_value is None or a < max_value:
        yield a
        a *= base
    while True:
        yield max_value


def decay(
    initial_value: float = 1,
    decay_factor: float = 1,
    min_value: float | None = None,
) -> Generator[float, Any, None]:
    """Generator for exponential decay[1]:

    Args:
        initial_value: initial quantity
        decay_factor: exponential decay constant.
        min_value: The minimum value to yield. Once the value in the
             true exponential sequence is lower than this, the value
             of min_value will forever after be yielded.

    [1] https://en.wikipedia.org/wiki/Exponential_decay
    """
    # Advance past initial .send() call
    yield 0
    a = initial_value
    min_value = min_value or 0.0
    while a > min_value:
        yield a
        a *= math.exp(-decay_factor)
    while True:
        yield min_value


def fibo(max_value: int | None = None) -> Generator[int, Any, None]:
    """Generator for fibonaccial decay.

    Args:
        max_value: The maximum value to yield. Once the value in the
             true fibonacci sequence exceeds this, the value
             of max_value will forever after be yielded.
    """
    # Advance past initial .send() call
    yield 0

    a = 1
    b = 1
    while max_value is None or a < max_value:
        yield a
        a, b = b, a + b
    while True:
        yield max_value


def constant(interval: float | Iterable[float] = 1) -> Generator[float, Any, None]:
    """Generator for constant intervals.

    Args:
        interval: A constant value to yield or an iterable of such values.
    """
    # Advance past initial .send() call
    yield 0

    itr = (
        itertools.repeat(interval)
        if isinstance(interval, (int, float))
        else iter(interval)
    )

    for val in itr:
        yield val


def capped(
    wait_gen: _WaitGenerator,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> _WaitGenerator:
    """Wraps a wait generator, clamping each value it yields.

    Useful for wait generators without their own bound, such as
    `constant` or `runtime` (e.g. capping a server-provided
    `Retry-After` value so a misbehaving server can't stall retries
    indefinitely):

        backoff.on_predicate(
            backoff.capped(backoff.runtime, max_value=60),
            predicate=lambda r: r.status_code == 429,
            value=lambda r: int(r.headers.get("Retry-After", 1)),
        )

    Args:
        wait_gen: The wait generator to wrap.
        min_value: The minimum value to yield. Values below this are
            raised to min_value.
        max_value: The maximum value to yield. Values above this are
            lowered to max_value.
    """

    def generator(**kwargs: Any) -> Generator[float, Any, None]:
        gen = wait_gen(**kwargs)
        gen.send(None)

        send_value = yield 0
        while True:
            value = gen.send(send_value)
            if max_value is not None:
                value = min(value, max_value)
            if min_value is not None:
                value = max(value, min_value)
            send_value = yield value

    return generator


def runtime(*, value: Callable[[Any], float]) -> Generator[float, Any, None]:
    """Generator that is based on parsing the return value or thrown
        exception of the decorated method

    Useful for honoring a server-specified retry delay, e.g. an HTTP
    `Retry-After` header, rather than a fixed wait sequence:

        # with on_predicate, `value` receives the return value
        @backoff.on_predicate(
            backoff.runtime,
            predicate=lambda r: r.status_code == 429,
            value=lambda r: int(r.headers.get("Retry-After", 1)),
        )
        def get_page():
            return requests.get(url)

        # with on_exception, `value` receives the raised exception
        @backoff.on_exception(
            backoff.runtime,
            RetryableError,
            value=lambda e: e.wait_seconds,
        )
        def get_page():
            ...

    Args:
        value: a callable which takes as input the decorated
            function's return value or thrown exception and
            determines how long to wait
    """
    ret_or_exc = yield 0
    while True:
        ret_or_exc = yield value(ret_or_exc)

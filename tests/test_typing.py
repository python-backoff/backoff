import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any

if sys.version_info >= (3, 11):
    from typing import assert_type
else:
    from typing_extensions import assert_type

import backoff

# No pyunit tests are defined here yet, but the following decorator calls will
# be analyzed by mypy which would have caught a bug the last release.


@backoff.on_exception(
    backoff.expo,
    ValueError,
    jitter=None,
    max_tries=3,
)
def foo() -> None:
    raise ValueError()


@backoff.on_exception(
    backoff.constant,
    ValueError,
    interval=1,
    max_tries=3,
)
def bar() -> None:
    raise ValueError()


@backoff.on_predicate(
    backoff.runtime,
    predicate=lambda r: r.status_code == 429,
    value=lambda r: int(r.headers.get("Retry-After")),
    jitter=None,
)
def baz() -> None:
    pass


# Regression test for https://github.com/python-backoff/backoff/issues/200:
# decorating an annotated async function must preserve its parameter and
# awaited result types, without reconstructing it as `Callable[P,
# Coroutine[Any, Any, T]]` (which mypy's `disallow_any_decorated` flags as
# leaking `Any`, since an async function is already typed that way).
@backoff.on_exception(backoff.expo, ValueError)
async def fetch(x: int) -> str:
    return str(x)


_typed_fetch: Callable[[int], Coroutine[Any, Any, str]] = fetch


async def _use_fetch() -> None:
    result = await asyncio.create_task(fetch(1))
    assert_type(result, str)

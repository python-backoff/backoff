import asyncio
import sys

if sys.version_info >= (3, 11):
    from typing import assert_type
else:
    from typing_extensions import assert_type

import backoff


@backoff.on_exception(backoff.expo, ValueError)
def fetch_sync_with_exception(value: str, *, suffix: str) -> str:
    return value + suffix


@backoff.on_predicate(backoff.expo)
def fetch_sync_with_predicate(value: str, *, suffix: str) -> str:
    return value + suffix


@backoff.on_exception(backoff.expo, ValueError)
async def fetch_async_with_exception(value: str, *, suffix: str) -> str:
    return value + suffix


@backoff.on_predicate(backoff.expo)
async def fetch_async_with_predicate(value: str, *, suffix: str) -> str:
    return value + suffix


def consume_sync_decorated_functions() -> None:
    exception_result = fetch_sync_with_exception("exception", suffix=" result")
    predicate_result = fetch_sync_with_predicate("predicate", suffix=" result")
    assert_type(exception_result, str)
    assert_type(predicate_result, str)


async def consume_async_decorated_functions() -> None:
    exception_result = await fetch_async_with_exception("exception", suffix=" result")
    predicate_result = await fetch_async_with_predicate("predicate", suffix=" result")
    assert_type(exception_result, str)
    assert_type(predicate_result, str)

    exception_task = asyncio.create_task(
        fetch_async_with_exception("exception", suffix=" task")
    )
    predicate_task = asyncio.create_task(
        fetch_async_with_predicate("predicate", suffix=" task")
    )
    assert_type(exception_task, asyncio.Task[str])
    assert_type(predicate_task, asyncio.Task[str])
    assert_type(await exception_task, str)
    assert_type(await predicate_task, str)

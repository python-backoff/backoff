# Async Support

Backoff fully supports Python's `async`/`await` syntax for asynchronous code.

## Basic Usage

Simply decorate async functions with the same decorators:

```python
import backoff
import aiohttp


@backoff.on_exception(backoff.expo, aiohttp.ClientError)
async def fetch_data(url):
    async with aiohttp.ClientSession() as session, session.get(url) as response:
        return await response.json()
```

## Async Event Handlers

Event handlers can be async when used with async functions:

```python
async def async_log_retry(details):
    await log_service.log(f"Retry {details['tries']} after {details['elapsed']:.1f}s")


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=async_log_retry,
)
async def async_operation():
    pass
```

## Common Patterns

### HTTP Client

```python
@backoff.on_exception(
    backoff.expo,
    aiohttp.ClientError,
    max_time=60,
)
async def get_url(url):
    async with aiohttp.ClientSession(raise_for_status=True) as session:  # noqa: SIM117
        async with session.get(url) as response:
            return await response.text()
```

### Database Operations

```python
import asyncpg


@backoff.on_exception(
    backoff.expo,
    asyncpg.PostgresError,
    max_tries=5,
)
async def query_database(pool, query):
    async with pool.acquire() as conn:
        return await conn.fetch(query)
```

### Concurrent Requests

```python
import asyncio


@backoff.on_exception(
    backoff.expo,
    aiohttp.ClientError,
    max_tries=3,
)
async def fetch_one(session, url):
    async with session.get(url) as response:
        return await response.json()


async def fetch_all(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_one(session, url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

## on_predicate with Async

```python
@backoff.on_predicate(
    backoff.constant,
    lambda result: result["status"] != "complete",
    interval=5,
    max_time=300,
)
async def poll_job_status(job_id):
    async with aiohttp.ClientSession() as session:  # noqa: SIM117
        async with session.get(f"/api/jobs/{job_id}") as response:
            return await response.json()
```

## Mixing Sync and Async

Sync handlers work with async functions:

```python
def sync_log(details):
    print(f"Retry {details['tries']}")


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=sync_log,  # Sync handler with async function
)
async def async_function():
    pass
```

But async handlers only work with async functions:

```python
async def async_log(details):
    await log_to_service(details)


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=async_log,  # Must be used with async function
)
async def async_function():
    pass
```

## Complete Example

```python
import asyncio
import aiohttp
import backoff
import logging

logger = logging.getLogger(__name__)


async def log_async_retry(details):
    logger.warning(
        f"Async retry {details['tries']}: "
        f"wait={details['wait']:.1f}s, "
        f"elapsed={details['elapsed']:.1f}s"
    )


@backoff.on_exception(
    backoff.expo,
    (
        aiohttp.ClientError,
        asyncio.TimeoutError,
    ),
    max_tries=5,
    max_time=60,
    on_backoff=log_async_retry,
)
async def robust_fetch(url, timeout=10):
    async with aiohttp.ClientSession() as session:  # noqa: SIM117
        async with session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            return await response.json()


# Usage
async def main():
    result = await robust_fetch("https://api.example.com/data")
    print(result)


asyncio.run(main())
```

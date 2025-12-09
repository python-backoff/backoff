# Getting Started

This guide will walk you through the basics of using backoff for retrying functions.

## Installation

Install backoff using pip:

```bash
pip install python-backoff
```

## Basic Concepts

Backoff provides two main decorators:

1. **`@backoff.on_exception`** - Retry when a specific exception is raised
2. **`@backoff.on_predicate`** - Retry when a condition is true about the return value

## Your First Retry

Let's start with a simple example - retrying a network request:

```python
import requests

import backoff


@backoff.on_exception(backoff.expo, requests.exceptions.RequestException)
def get_url(url):
    return requests.get(url)
```

This decorator will:

- Retry whenever `RequestException` (or any subclass) is raised
- Use **exponential backoff** (wait times: 1s, 2s, 4s, 8s, 16s, ...)
- Keep retrying indefinitely until success

## Adding Limits

In production, you'll want to limit retries:

```python
@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_time=60,
    max_tries=5,
)
def get_url(url):
    return requests.get(url)
```

This will give up after either:

- 60 seconds have elapsed, OR
- 5 retry attempts have been made

## Handling Multiple Exceptions

You can retry on multiple exception types:

```python
@backoff.on_exception(
    backoff.expo,
    (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
    max_time=30,
)
def get_url(url):
    return requests.get(url)
```

## Conditional Give-Up

Sometimes you need custom logic to decide when to stop retrying:

```python
def fatal_code(e):
    """Don't retry on 4xx errors"""
    return 400 <= e.response.status_code < 500


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_time=300,
    giveup=fatal_code,
)
def get_url(url):
    return requests.get(url)
```

## Using on_predicate

For polling or checking return values:

```python
@backoff.on_predicate(
    backoff.constant,
    lambda result: result is None,
    interval=5,
    max_time=300,
)
def check_job_status(job_id):
    response = requests.get(f"/jobs/{job_id}")
    if response.json()["status"] == "complete":
        return response.json()
    return None  # Will trigger retry
```

## Wait Strategies

Backoff provides several wait strategies:

### Exponential (expo)

```python
@backoff.on_exception(backoff.expo, Exception)
def my_function(): ...
```

Wait times: 1s, 2s, 4s, 8s, 16s, ...

### Fibonacci (fibo)

```python
@backoff.on_exception(backoff.fibo, Exception)
def my_function(): ...
```

Wait times: 1s, 1s, 2s, 3s, 5s, 8s, 13s, ...

### Constant

```python
@backoff.on_exception(backoff.constant, Exception, interval=5)
def my_function(): ...
```

Wait times: 5s, 5s, 5s, 5s, ...

## Event Handlers

Track what's happening during retries:

```python
def log_backoff(details):
    print(
        f"Backing off {details['wait']:.1f} seconds after "
        f"{details['tries']} tries"
    )


def log_success(details):
    print(f"Success after {details['tries']} tries")


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    on_backoff=log_backoff,
    on_success=log_success,
    max_tries=5,
)
def get_url(url):
    return requests.get(url)
```

## Async Support

Backoff works seamlessly with async functions:

```python
import aiohttp


@backoff.on_exception(backoff.expo, aiohttp.ClientError, max_time=60)
async def get_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()
```

## Next Steps

- [Decorators Guide](user-guide/decorators.md) - Deep dive into decorators
- [Wait Strategies](user-guide/wait-strategies.md) - All available strategies
- [Configuration](user-guide/configuration.md) - Advanced configuration options
- [Examples](examples.md) - Real-world examples

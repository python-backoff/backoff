# Wait Strategies

Backoff provides several built-in wait strategies (generators) that determine how long to wait between retries.

## Exponential (expo)

Exponential backoff doubles the wait time after each retry.

```python
import backoff


@backoff.on_exception(backoff.expo, Exception)
def my_function():
    pass
```

**Wait sequence (without jitter):** 1s, 2s, 4s, 8s, 16s, 32s, ...

### Parameters

- **base** - Base wait time in seconds (default: 1)
- **factor** - Multiplier for each iteration (default: 2)
- **max_value** - Maximum wait time cap (default: None)

### Examples

```python
# Custom base and factor
@backoff.on_exception(
    backoff.expo,
    Exception,
    base=2,  # Start at 2 seconds
    factor=3,  # Triple each time
    max_value=60,  # Cap at 60 seconds
)
def custom_expo():
    pass


# Wait sequence: 2s, 6s, 18s, 54s, 60s, 60s, ...
```

### Best For

- API rate limiting
- Network requests
- Database connections
- Most general-purpose retries

## Fibonacci (fibo)

Fibonacci backoff follows the Fibonacci sequence.

```python
@backoff.on_exception(backoff.fibo, Exception)
def my_function():
    pass
```

**Wait sequence (without jitter):** 1s, 1s, 2s, 3s, 5s, 8s, 13s, 21s, ...

### Parameters

- **max_value** - Maximum wait time cap (default: None)

### Examples

```python
@backoff.on_exception(
    backoff.fibo,
    Exception,
    max_value=30,  # Cap at 30 seconds
)
def fibo_with_cap():
    pass


# Wait sequence: 1s, 1s, 2s, 3s, 5s, 8s, 13s, 21s, 30s, 30s, ...
```

### Best For

- Gradual backoff when you want slower growth than exponential
- Polling operations
- Resource-constrained environments

## Constant

Fixed wait time between all retries.

```python
@backoff.on_exception(
    backoff.constant,
    Exception,
    interval=5,  # Always wait 5 seconds
)
def my_function():
    pass
```

**Wait sequence:** 5s, 5s, 5s, 5s, ...

### Parameters

- **interval** - Wait time in seconds (default: 1)

### Examples

```python
# Poll every 10 seconds
@backoff.on_predicate(
    backoff.constant,
    interval=10,
    jitter=None,  # Disable jitter for exact intervals
    max_time=300,
)
def poll_every_10_seconds():
    pass
```

### Best For

- Regular polling
- Fixed-rate retry policies
- Cases where jitter is disabled

## Runtime

Dynamic wait time based on function return value or exception.

```python
@backoff.on_predicate(
    backoff.runtime,
    predicate=lambda r: r.status_code == 429,
    value=lambda r: int(r.headers.get("Retry-After", 1)),
)
def respect_retry_after():
    return requests.get(url)
```

### Parameters

- **value** - Function that extracts wait time from return value or exception

### Examples

#### HTTP Retry-After Header

```python
def get_retry_after(response):
    """Extract Retry-After from HTTP response"""
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            return int(retry_after)
    return 1  # Default


@backoff.on_predicate(
    backoff.runtime,
    predicate=lambda r: r.status_code == 429,
    value=get_retry_after,
    jitter=None,
)
def api_call():
    return requests.get(api_url)
```

#### Exception-based Wait Time

```python
class RetryableError(Exception):
    def __init__(self, message, wait_seconds):
        super().__init__(message)
        self.wait_seconds = wait_seconds


@backoff.on_exception(backoff.runtime, RetryableError, value=lambda e: e.wait_seconds)
def custom_retry():
    raise RetryableError("Try again", wait_seconds=30)
```

### Best For

- Respecting server-specified retry delays
- Custom retry logic from application responses
- API rate limiting with Retry-After headers

## Jitter

All wait strategies support jitter to add randomness and prevent thundering herd problems.

### full_jitter (default)

Uses AWS's Full Jitter algorithm - wait time is random between 0 and the calculated wait.

```python
@backoff.on_exception(backoff.expo, Exception)
def my_function():
    pass


# Equivalent to:
@backoff.on_exception(backoff.expo, Exception, jitter=backoff.full_jitter)
def my_function():
    pass
```

For exponential backoff: actual wait is random between 0 and 2^n seconds.

### random_jitter

Adds random milliseconds (0-1000ms) to the calculated wait time.

```python
@backoff.on_exception(backoff.expo, Exception, jitter=backoff.random_jitter)
def my_function():
    pass
```

### Custom Jitter

```python
import random


def custom_jitter(value):
    """Add 10-50% randomness"""
    jitter_amount = value * random.uniform(0.1, 0.5)
    return value + jitter_amount


@backoff.on_exception(backoff.expo, Exception, jitter=custom_jitter)
def my_function():
    pass
```

### Disable Jitter

```python
@backoff.on_exception(backoff.expo, Exception, jitter=None)
def my_function():
    pass
```

## Comparison

| Strategy | Growth Rate | Use Case | Example Sequence (5 iterations) |
|----------|------------|----------|--------------------------------|
| **expo** | Fast | Network, APIs | 1s, 2s, 4s, 8s, 16s |
| **fibo** | Medium | Polling | 1s, 1s, 2s, 3s, 5s |
| **constant** | None | Fixed intervals | 5s, 5s, 5s, 5s, 5s |
| **runtime** | Variable | Server-directed | Depends on response |

## Choosing a Strategy

**Use exponential when:**

- You want fast backoff for transient failures
- Dealing with network or API calls
- Following industry best practices

**Use fibonacci when:**

- You want gentler backoff than exponential
- Resource constraints matter
- Polling for long-running operations

**Use constant when:**

- You need predictable, fixed intervals
- Polling at specific rates
- Testing or debugging

**Use runtime when:**

- Server tells you how long to wait
- Retry delay is in the response/exception
- Implementing Retry-After headers

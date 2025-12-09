# Configuration

Complete guide to configuring backoff decorators.

## Retry Limits

### max_tries

Maximum number of function call attempts.

```python
@backoff.on_exception(backoff.expo, Exception, max_tries=5)
def my_function():
    pass
```

- First call counts as try #1
- Will make up to 5 total attempts
- After 5 failures, gives up and raises exception

### max_time

Maximum total elapsed time in seconds.

```python
@backoff.on_exception(backoff.expo, Exception, max_time=60)
def my_function():
    pass
```

- Tracks total time from first attempt
- Gives up when time limit is reached
- Useful for time-sensitive operations

### Combining Limits

Use both to create flexible retry policies:

```python
@backoff.on_exception(backoff.expo, Exception, max_tries=10, max_time=300)
def my_function():
    pass
```

Stops when **either** condition is met.

## Runtime Configuration

Pass callables instead of constants for dynamic configuration:

```python
class Config:
    MAX_RETRIES = 5
    MAX_TIME = 60


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=lambda: Config.MAX_RETRIES,
    max_time=lambda: Config.MAX_TIME,
)
def configurable_function():
    pass


# Can change at runtime
Config.MAX_RETRIES = 10
```

### Environment-Based Configuration

```python
import os


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=lambda: int(os.getenv("MAX_RETRIES", "5")),
    max_time=lambda: int(os.getenv("MAX_TIME", "60")),
)
def env_configured():
    pass
```

## Wait Generator Configuration

Each wait strategy accepts different parameters.

### Exponential Parameters

```python
@backoff.on_exception(
    backoff.expo,
    Exception,
    base=2,  # Base wait time
    factor=2,  # Multiplication factor
    max_value=60,  # Maximum wait time
)
def expo_config():
    pass
```

### Fibonacci Parameters

```python
@backoff.on_exception(
    backoff.fibo,
    Exception,
    max_value=30,  # Maximum wait time
)
def fibo_config():
    pass
```

### Constant Parameters

```python
@backoff.on_exception(
    backoff.constant,
    Exception,
    interval=5,  # Fixed interval in seconds
)
def constant_config():
    pass
```

### Runtime Parameters

```python
@backoff.on_predicate(
    backoff.runtime,
    predicate=lambda r: r.status_code == 429,
    value=lambda r: int(r.headers.get("Retry-After", 1)),
)
def runtime_config():
    return requests.get(url)
```

## Jitter Configuration

Control randomization of wait times.

### Full Jitter (Default)

```python
@backoff.on_exception(backoff.expo, Exception)
def my_function():
    pass


# Same as:
@backoff.on_exception(backoff.expo, Exception, jitter=backoff.full_jitter)
def my_function():
    pass
```

Wait time is random between 0 and calculated value.

### Random Jitter

```python
@backoff.on_exception(backoff.expo, Exception, jitter=backoff.random_jitter)
def my_function():
    pass
```

Adds 0-1000ms to calculated value.

### No Jitter

```python
@backoff.on_exception(backoff.expo, Exception, jitter=None)
def my_function():
    pass
```

Exact wait times, no randomization.

### Custom Jitter

```python
import random


def custom_jitter(value):
    return value * random.uniform(0.8, 1.2)


@backoff.on_exception(backoff.expo, Exception, jitter=custom_jitter)
def my_function():
    pass
```

## Give-Up Conditions

### Basic giveup

```python
def should_giveup(e):
    return isinstance(e, ValueError)


@backoff.on_exception(backoff.expo, Exception, giveup=should_giveup)
def my_function():
    pass
```

### HTTP Status Code Conditions

```python
def fatal_error(e):
    if hasattr(e, "response"):
        status = e.response.status_code
        # Don't retry client errors except rate limiting
        return 400 <= status < 500 and status != 429
    return False


@backoff.on_exception(
    backoff.expo, requests.exceptions.RequestException, giveup=fatal_error
)
def api_call():
    pass
```

### Multiple Conditions

```python
def complex_giveup(e):
    # Give up on authentication errors
    if "authentication" in str(e).lower():
        return True

    # Give up on 4xx except 429
    if hasattr(e, "response"):
        status = e.response.status_code
        if 400 <= status < 500 and status != 429:
            return True

    return False
```

### raise_on_giveup

Control whether to raise exception when giving up:

```python
# Default: raises exception
@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def raises_on_failure():
    pass


# Returns None instead
@backoff.on_exception(backoff.expo, Exception, max_tries=3, raise_on_giveup=False)
def returns_none_on_failure():
    pass
```

## Predicate Configuration

For `on_predicate` decorator.

### Default Predicate (Falsey Check)

```python
@backoff.on_predicate(backoff.constant, interval=2)
def wait_for_truthy():
    return get_result() or None
```

### Custom Predicate

```python
def needs_retry(result):
    return result.get("status") == "pending"


@backoff.on_predicate(backoff.expo, needs_retry, max_time=300)
def poll_status():
    return api.get_status()
```

### Multiple Conditions

```python
def should_retry(result):
    if result is None:
        return True
    if not result.get("ready"):
        return True
    if result.get("status") == "processing":
        return True
    return False


@backoff.on_predicate(backoff.fibo, should_retry, max_value=60)
def complex_poll():
    return get_resource()
```

## Best Practices

### API Calls

```python
@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_tries=5,
    max_time=60,
    giveup=lambda e: 400 <= getattr(e.response, "status_code", 500) < 500,
)
def api_request():
    pass
```

### Database Operations

```python
@backoff.on_exception(
    backoff.expo, sqlalchemy.exc.OperationalError, max_tries=3, max_time=30
)
def db_query():
    pass
```

### Polling

```python
@backoff.on_predicate(
    backoff.constant,
    lambda result: result["status"] != "complete",
    interval=5,
    jitter=None,
    max_time=600,
)
def poll_job():
    return check_job_status()
```

### Long-Running Operations

```python
@backoff.on_predicate(
    backoff.fibo,
    lambda result: not result.is_ready(),
    max_value=60,
    max_time=3600,  # 1 hour
)
def wait_for_completion():
    return check_operation()
```

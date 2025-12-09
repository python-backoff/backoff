# Decorators

Detailed guide to backoff decorators.

## on_exception

The `on_exception` decorator retries a function when a specified exception is raised.

### Basic Usage

```python
import backoff
import requests


@backoff.on_exception(backoff.expo, requests.exceptions.RequestException)
def get_url(url):
    return requests.get(url)
```

### Parameters

- **wait_gen** - Wait strategy generator (expo, fibo, constant, runtime)
- **exception** - Exception class or tuple of exception classes to catch
- **max_tries** - Maximum number of attempts (default: None = unlimited)
- **max_time** - Maximum total time in seconds (default: None = unlimited)
- **jitter** - Jitter function to add randomness (default: full_jitter)
- **giveup** - Function to determine if exception is non-retryable
- **on_success** - Callback when function succeeds
- **on_backoff** - Callback when backing off
- **on_giveup** - Callback when giving up
- **raise_on_giveup** - Whether to raise exception on giveup (default: True)
- **logger** - Logger for retry events (default: 'backoff' logger)

### Multiple Exceptions

Handle different exceptions with the same backoff:

```python
@backoff.on_exception(
    backoff.expo,
    (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.HTTPError,
    ),
)
def make_request(url):
    return requests.get(url)
```

### Conditional Giveup

Customize when to stop retrying:

```python
def is_fatal(e):
    """Don't retry on client errors"""
    if hasattr(e, "response") and e.response is not None:
        return 400 <= e.response.status_code < 500
    return False


@backoff.on_exception(
    backoff.expo, requests.exceptions.RequestException, giveup=is_fatal, max_time=300
)
def api_call(endpoint):
    response = requests.get(endpoint)
    response.raise_for_status()
    return response.json()
```

### Suppress Exceptions on Giveup

Return None instead of raising when all retries are exhausted:

```python
@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_tries=5,
    raise_on_giveup=False,
)
def optional_request(url):
    return requests.get(url)


# Returns None if all retries fail
result = optional_request("https://example.com")
```

## on_predicate

The `on_predicate` decorator retries when a condition is true about the return value.

### Basic Usage

```python
@backoff.on_predicate(backoff.fibo, lambda x: x is None, max_value=13)
def poll_for_result(job_id):
    result = check_job(job_id)
    return result if result else None
```

### Parameters

- **wait_gen** - Wait strategy generator (expo, fibo, constant, runtime)
- **predicate** - Function that returns True if retry is needed (default: falsey check)
- **max_tries** - Maximum number of attempts (default: None = unlimited)
- **max_time** - Maximum total time in seconds (default: None = unlimited)
- **jitter** - Jitter function to add randomness (default: full_jitter)
- **on_success** - Callback when predicate returns False
- **on_backoff** - Callback when predicate returns True
- **on_giveup** - Callback when giving up
- **logger** - Logger for retry events (default: 'backoff' logger)

### Default Predicate (Falsey Check)

When no predicate is specified, the decorator retries on falsey values:

```python
@backoff.on_predicate(backoff.constant, interval=2, max_time=60)
def wait_for_resource():
    # Retries until a truthy value is returned
    return resource.get() or None
```

### Custom Predicates

Define specific conditions for retry:

```python
@backoff.on_predicate(
    backoff.expo, lambda result: result["status"] == "pending", max_time=600
)
def poll_job_status(job_id):
    return api.get_job(job_id)
```

### Combining Predicates

```python
def needs_retry(result):
    return (
        result is None
        or result.get("status") in ["pending", "processing"]
        or not result.get("ready", False)
    )


@backoff.on_predicate(backoff.fibo, needs_retry, max_value=60)
def complex_poll(resource_id):
    return api.get_resource(resource_id)
```

## Combining Decorators

Stack multiple decorators for complex retry logic:

```python
@backoff.on_predicate(backoff.fibo, lambda x: x is None, max_value=13)
@backoff.on_exception(backoff.expo, requests.exceptions.HTTPError, max_time=60)
@backoff.on_exception(backoff.expo, requests.exceptions.Timeout, max_time=300)
def robust_poll(endpoint):
    response = requests.get(endpoint)
    response.raise_for_status()
    data = response.json()
    return data if data.get("ready") else None
```

The decorators are applied from bottom to top (inside out), so:

1. Timeout exceptions get up to 300s of retries
2. HTTP errors get up to 60s of retries
3. None results trigger fibonacci backoff up to 13s

## Event Handler Details

Event handlers receive a dictionary with these keys:

```python
{
    "target": my_function,  # function reference
    "args": (arg1, arg2),  # positional args tuple
    "kwargs": {"key": "value"},  # keyword args dict
    "tries": 3,  # number of tries so far
    "elapsed": 1.5,  # elapsed time in seconds
    "wait": 2.0,  # seconds to wait (on_backoff only)
    "value": None,  # return value (on_predicate only)
    "exception": Exception(),  # exception (on_exception only)
}
```

Example handler:

```python
def detailed_log(details):
    print(
        f"Try {details['tries']}: "
        f"elapsed={details['elapsed']:.2f}s, "
        f"wait={details.get('wait', 0):.2f}s"
    )


@backoff.on_exception(backoff.expo, Exception, on_backoff=detailed_log, max_tries=5)
def my_function():
    pass
```

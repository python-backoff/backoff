# Combining Decorators

Stack multiple backoff decorators for complex retry logic.

## Basics

Decorators are applied from bottom to top (inside out):

```python
@backoff.on_predicate(backoff.fibo, lambda x: x is None)  # Applied last
@backoff.on_exception(backoff.expo, HTTPError)  # Applied second
@backoff.on_exception(backoff.expo, Timeout)  # Applied first
def complex_operation():
    pass
```

## Common Patterns

### Different Exceptions, Different Strategies

```python
@backoff.on_exception(
    backoff.expo,
    requests.exceptions.Timeout,
    max_time=300,  # Generous timeout for network issues
)
@backoff.on_exception(
    backoff.expo,
    requests.exceptions.HTTPError,
    max_time=60,  # Shorter timeout for HTTP errors
    giveup=lambda e: 400 <= e.response.status_code < 500,
)
def api_call(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()
```

### Exception + Predicate

```python
@backoff.on_predicate(
    backoff.constant,
    lambda result: result.get("status") == "pending",
    interval=5,
    max_time=600,
)
@backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_time=60)
def poll_until_ready(job_id):
    response = requests.get(f"/api/jobs/{job_id}")
    response.raise_for_status()
    return response.json()
```

## Execution Order

Inner decorators execute first:

```python
calls = []


def track_call(func_name):
    def handler(details):
        calls.append(func_name)

    return handler


@backoff.on_exception(
    backoff.constant,
    ValueError,
    on_backoff=track_call("outer"),
    max_tries=2,
    interval=0.01,
)
@backoff.on_exception(
    backoff.constant,
    TypeError,
    on_backoff=track_call("inner"),
    max_tries=2,
    interval=0.01,
)
def failing_function(error_type):
    raise error_type("Test")
```

- If `TypeError` raised: inner decorator retries
- If `ValueError` raised: outer decorator retries
- Both errors: inner handles TypeError, then outer handles ValueError

## Best Practices

### Specific Before General

```python
@backoff.on_exception(backoff.expo, Exception)  # Catch-all
@backoff.on_exception(backoff.fibo, ConnectionError)  # Specific
def network_operation():
    pass
```

### Short Timeouts Inside, Long Outside

```python
@backoff.on_exception(
    backoff.expo,
    Exception,
    max_time=600,  # Overall 10-minute limit
)
@backoff.on_exception(
    backoff.constant,
    Timeout,
    interval=1,
    max_tries=3,  # Quick retries for timeouts
)
def layered_retry():
    pass
```

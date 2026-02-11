# Frequently Asked Questions

## General Questions

### What is backoff?

Backoff is a Python library that provides decorators for retrying functions when they fail or don't meet certain conditions. It's commonly used for handling transient failures in network requests, API calls, database operations, and other unreliable operations.

### When should I use backoff?

Use backoff when:

- Making network requests that might fail temporarily
- Calling external APIs with rate limits
- Connecting to databases that might be temporarily unavailable
- Polling for results from async operations
- Handling any operation that might fail transiently

### How is backoff different from just using a loop?

Backoff provides:

- Automatic retry logic with configurable strategies
- Built-in exponential/fibonacci/constant wait patterns
- Jitter to prevent thundering herd
- Event handlers for logging and monitoring
- Clean decorator syntax
- Async/await support
- Type hints and better IDE support

## Configuration Questions

### How do I limit the number of retries?

Use `max_tries`:

```python
@backoff.on_exception(backoff.expo, Exception, max_tries=5)
def my_function():
    pass
```

### How do I limit the total time spent retrying?

Use `max_time` (in seconds):

```python
@backoff.on_exception(backoff.expo, Exception, max_time=60)
def my_function():
    pass
```

### Can I use both max_tries and max_time?

Yes! The function will stop retrying when either limit is reached:

```python
@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=10,
    max_time=300,
)
def my_function():
    pass
```

### How do I disable jitter?

Pass `jitter=None`:

```python
@backoff.on_exception(backoff.expo, Exception, jitter=None)
def my_function():
    pass
```

This gives you predictable wait times, useful for testing or when exact timing matters.

## Exception Handling

### Which exceptions should I retry?

Retry transient failures (temporary issues):

- ✅ Network timeouts
- ✅ Connection errors
- ✅ 5xx server errors
- ✅ 429 rate limiting
- ✅ Database connection failures

Don't retry permanent failures:

- ❌ 4xx client errors (except 429)
- ❌ Authentication failures
- ❌ Validation errors
- ❌ Resource not found errors

### How do I stop retrying for certain errors?

Use the `giveup` parameter:

```python
def is_permanent_error(e):
    if hasattr(e, "response"):
        return 400 <= e.response.status_code < 500
    return False


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    giveup=is_permanent_error,
)
def api_call():
    pass
```

### What happens when retries are exhausted?

By default (`raise_on_giveup=True`), the original exception is re-raised. You can disable this:

```python
@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=5,
    raise_on_giveup=False,
)
def my_function():
    pass


result = my_function()  # Returns None if all retries fail
```

### Can I retry multiple exception types?

Yes, pass a tuple:

```python
@backoff.on_exception(
    backoff.expo,
    (
        TimeoutError,
        ConnectionError,
        requests.exceptions.RequestException,
    ),
)
def my_function():
    pass
```

## Wait Strategy Questions

### Which wait strategy should I use?

- **Exponential** (`backoff.expo`) - Most common, fast backoff for network/API calls
- **Fibonacci** (`backoff.fibo`) - Gentler backoff, good for polling
- **Constant** (`backoff.constant`) - Fixed intervals, good for regular polling
- **Runtime** (`backoff.runtime`) - Server-directed wait times (Retry-After headers)

### What is jitter and why is it important?

Jitter adds randomness to wait times to prevent the "thundering herd" problem (many clients retrying simultaneously). The default `full_jitter` uses AWS's algorithm where actual wait time is random between 0 and the calculated wait time.

### How do I respect Retry-After headers?

Use `backoff.runtime`:

```python
@backoff.on_predicate(
    backoff.runtime,
    predicate=lambda r: r.status_code == 429,
    value=lambda r: int(r.headers.get("Retry-After", 1)),
    jitter=None,
)
def api_call():
    return requests.get(url)
```

## Async Questions

### Does backoff work with async/await?

Yes! Just decorate async functions:

```python
@backoff.on_exception(backoff.expo, aiohttp.ClientError)
async def fetch_data(url):
    async with aiohttp.ClientSession() as session, session.get(url) as response:
        return await response.json()
```

### Can event handlers be async?

Yes, you can use async functions for `on_success`, `on_backoff`, and `on_giveup`:

```python
async def log_retry(details):
    await async_logger.log(f"Retry {details['tries']}")


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=log_retry,
)
async def my_function():
    pass
```

## Logging and Monitoring

### How do I log retry attempts?

Use event handlers:

```python
def log_backoff(details):
    logger.warning("Retry %d after %.1fs", details["tries"], details["elapsed"])


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=log_backoff,
)
def my_function():
    pass
```

### Can I use the default logger?

Yes, backoff has a default logger. Enable it:

```python
import logging

logging.getLogger("backoff").addHandler(logging.StreamHandler())
logging.getLogger("backoff").setLevel(logging.INFO)
```

### How do I disable all logging?

Pass `logger=None`:

```python
@backoff.on_exception(backoff.expo, Exception, logger=None)
def my_function():
    pass
```

### What information is available in event handlers?

Event handlers receive a dict with:

- `target` - Function being called
- `args` - Positional arguments
- `kwargs` - Keyword arguments
- `tries` - Number of attempts
- `elapsed` - Total elapsed time
- `wait` - Time to wait (on_backoff only)
- `value` - Return value (on_predicate only)
- `exception` - Exception raised (on_exception only)

## Performance Questions

### Does backoff add overhead?

Minimal. The decorator overhead is negligible compared to typical network/database operation times.

### Can I use backoff in production?

Absolutely! Backoff is used in production by thousands of projects. It's stable, well-tested, and maintained.

### How many retries is too many?

It depends on your use case:

- **Quick operations**: 3-5 retries
- **Network requests**: 5-10 retries with max_time=60s
- **Long polling**: Higher retries or no limit with max_time

### Will backoff cause memory leaks?

No. Backoff doesn't store state between function calls.

## Advanced Usage

### Can I combine multiple decorators?

Yes! Stack them for complex retry logic:

```python
@backoff.on_predicate(backoff.fibo, lambda x: x is None)
@backoff.on_exception(backoff.expo, HTTPError)
@backoff.on_exception(backoff.expo, Timeout)
def complex_operation():
    pass
```

Decorators are applied inside-out (bottom to top).

### How do I implement a circuit breaker?

Use the `giveup` callback with stateful logic:

```python
class CircuitBreaker:
    def __init__(self, threshold=5):
        self.failures = 0
        self.threshold = threshold
        self.opened_at = None

    def should_giveup(self, e):
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.time()
            return True
        return False


breaker = CircuitBreaker()


@backoff.on_exception(
    backoff.expo,
    Exception,
    giveup=breaker.should_giveup,
)
def protected_call():
    pass
```

### Can I use runtime configuration?

Yes, pass callables instead of values:

```python
def get_max_time():
    return app.config["RETRY_MAX_TIME"]


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_time=get_max_time,
)
def my_function():
    pass
```

### How do I test code that uses backoff?

1. Set `max_tries=1` or `jitter=None` for predictable tests
2. Mock the underlying operation to control failures
3. Use event handlers to verify retry behavior

```python
def test_retry_behavior():
    attempts = []

    def track_attempts(details):
        attempts.append(details["tries"])

    @backoff.on_exception(
        backoff.constant,
        ValueError,
        on_backoff=track_attempts,
        max_tries=3,
        interval=0.01,
    )
    def failing_function():
        raise ValueError("Test error")

    with pytest.raises(ValueError):
        failing_function()

    assert len(attempts) == 2  # Backoff called 2 times (3 tries total)
```

## Troubleshooting

### Why is my function not retrying?

Check:

1. Are you catching the right exception?
2. Is `max_tries` or `max_time` too low?
3. Is your `giveup` function returning True?
4. Are you actually calling the decorated function?

### Why are wait times not what I expect?

The default `full_jitter` adds randomness. To see exact wait times, disable jitter:

```python
@backoff.on_exception(backoff.expo, Exception, jitter=None)
def my_function():
    pass
```

### Can I see what's happening during retries?

Enable logging or use event handlers:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("backoff").setLevel(logging.DEBUG)
```

Or:

```python
@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=lambda d: print(f"Try {d['tries']}, wait {d['wait']:.1f}s"),
)
def my_function():
    pass
```

## Migration and Alternatives

### How does backoff compare to tenacity?

Both are excellent retry libraries. Backoff:

- Simpler, more focused API
- Decorator-first design
- Lighter weight
- More emphasis on wait strategies

Tenacity:

- More features (stop/wait/retry strategies)
- More complex configuration options
- More actively maintained recently

### Can I migrate from retrying or retry?

Yes, but the API is different. Backoff uses decorators with different parameter names.

### Is backoff still maintained?

Yes, backoff is actively maintained. Check the [GitHub repository](https://github.com/python-backoff/backoff) for recent activity.

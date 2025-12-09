# Event Handlers

Use event handlers to monitor, log, and react to retry events.

## Overview

Backoff decorators accept three types of event handlers:

- **on_success** - Called when function succeeds
- **on_backoff** - Called before each retry wait
- **on_giveup** - Called when all retries are exhausted

## Handler Signature

All handlers must accept a single `dict` argument containing event details:

```python
def my_handler(details):
    print(f"Event details: {details}")
```

## Available Details

The `details` dict contains:

| Key | Type | Description | Available In |
|-----|------|-------------|--------------|
| `target` | function | Function being called | All handlers |
| `args` | tuple | Positional arguments | All handlers |
| `kwargs` | dict | Keyword arguments | All handlers |
| `tries` | int | Number of attempts so far | All handlers |
| `elapsed` | float | Total elapsed time (seconds) | All handlers |
| `wait` | float | Seconds to wait before retry | `on_backoff` |
| `value` | any | Return value that triggered retry | `on_predicate` + `on_backoff/giveup` |
| `exception` | Exception | Exception that was raised | `on_exception` + `on_backoff/giveup` |

## on_success Handler

Called when the function completes successfully.

```python
def log_success(details):
    print(
        f"{details['target'].__name__} succeeded after "
        f"{details['tries']} tries"
    )


@backoff.on_exception(backoff.expo, Exception, on_success=log_success)
def my_function():
    pass
```

## on_backoff Handler

Called before each retry wait period.

```python
def log_backoff(details):
    print(
        f"Backing off {details['wait']:.1f}s after {details['tries']} tries "
        f"(elapsed: {details['elapsed']:.1f}s)"
    )


@backoff.on_exception(backoff.expo, Exception, on_backoff=log_backoff)
def my_function():
    pass
```

### Accessing Exception Info

For `on_exception`, the exception is available:

```python
def log_exception_backoff(details):
    exc = details.get("exception")
    print(f"Retrying due to: {type(exc).__name__}: {exc}")


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    on_backoff=log_exception_backoff,
)
def api_call():
    pass
```

### Accessing Return Value

For `on_predicate`, the return value is available:

```python
def log_value_backoff(details):
    value = details.get("value")
    print(f"Retrying because value was: {value}")


@backoff.on_predicate(
    backoff.constant,
    lambda x: x is None,
    on_backoff=log_value_backoff,
    interval=2,
)
def poll_resource():
    pass
```

## on_giveup Handler

Called when retries are exhausted.

```python
def log_giveup(details):
    print(
        f"Giving up on {details['target'].__name__} "
        f"after {details['tries']} tries and {details['elapsed']:.1f}s"
    )


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_giveup=log_giveup,
    max_tries=5,
)
def my_function():
    pass
```

## Multiple Handlers

You can provide multiple handlers as a list:

```python
def log_to_console(details):
    print(f"Retry #{details['tries']}")


def log_to_file(details):
    with open("retries.log", "a") as f:
        f.write(f"Retry #{details['tries']}\\n")


def send_metric(details):
    metrics.increment("retry_count")


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=[log_to_console, log_to_file, send_metric],
)
def my_function():
    pass
```

## Common Patterns

### Structured Logging

```python
import json
import logging

logger = logging.getLogger(__name__)


def structured_log_backoff(details):
    logger.warning(
        json.dumps(
            {
                "event": "retry",
                "function": details["target"].__name__,
                "tries": details["tries"],
                "wait": details["wait"],
                "elapsed": details["elapsed"],
            }
        )
    )


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=structured_log_backoff,
)
def my_function():
    pass
```

### Metrics Collection

```python
from prometheus_client import Counter, Histogram

retry_counter = Counter("backoff_retries_total", "Total retries", ["function"])
retry_duration = Histogram("backoff_retry_duration_seconds", "Retry duration")


def record_metrics(details):
    retry_counter.labels(function=details["target"].__name__).inc()
    retry_duration.observe(details["elapsed"])


@backoff.on_exception(backoff.expo, Exception, on_backoff=record_metrics)
def monitored_function():
    pass
```

### Error Tracking

```python
import sentry_sdk


def report_to_sentry(details):
    if details["tries"] > 3:  # Only report after 3 failures
        sentry_sdk.capture_message(
            f"Multiple retries for {details['target'].__name__}",
            level="warning",
            extra=details,
        )


@backoff.on_exception(backoff.expo, Exception, on_backoff=report_to_sentry)
def my_function():
    pass
```

### Alerting

```python
def alert_on_giveup(details):
    if details["tries"] >= 5:
        send_alert(
            f"Function {details['target'].__name__} failed "
            f"after {details['tries']} attempts"
        )


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_giveup=alert_on_giveup,
    max_tries=5,
)
def critical_function():
    pass
```

## Async Event Handlers

Event handlers can be async when used with async functions:

```python
import aiohttp


async def async_log_backoff(details):
    async with aiohttp.ClientSession() as session:
        await session.post("http://log-service/events", json=details)


@backoff.on_exception(backoff.expo, Exception, on_backoff=async_log_backoff)
async def async_function():
    pass
```

## Exception Access

In `on_exception` handlers, you can access exception info:

```python
import sys
import traceback


def detailed_exception_log(details):
    exc_type, exc_value, exc_tb = sys.exc_info()
    tb_str = "".join(traceback.format_tb(exc_tb))

    logger.error(
        f"Retry {details['tries']} due to {exc_type.__name__}: {exc_value}\\n"
        f"Traceback:\\n{tb_str}"
    )


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=detailed_exception_log,
)
def my_function():
    pass
```

## Conditional Handlers

Execute handler logic conditionally:

```python
def conditional_alert(details):
    # Only alert after many retries
    if details["tries"] >= 5:
        send_alert(f"High retry count: {details['tries']}")

    # Only log errors, not warnings
    if details.get("exception"):
        if isinstance(details["exception"], CriticalError):
            logger.error("Critical error during retry")


@backoff.on_exception(backoff.expo, Exception, on_backoff=conditional_alert)
def my_function():
    pass
```

## Complete Example

```python
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def log_attempt(details):
    logger.info(
        f"[{datetime.now()}] Attempt {details['tries']} "
        f"for {details['target'].__name__}"
    )


def log_backoff(details):
    logger.warning(
        f"Backing off {details['wait']:.1f}s after {details['tries']} tries. "
        f"Total elapsed: {details['elapsed']:.1f}s. "
        f"Error: {details.get('exception', 'N/A')}"
    )


def log_giveup(details):
    logger.error(
        f"Gave up on {details['target'].__name__} after "
        f"{details['tries']} tries and {details['elapsed']:.1f}s. "
        f"Final error: {details.get('exception', 'N/A')}"
    )


def log_success(details):
    logger.info(
        f"Success for {details['target'].__name__} after "
        f"{details['tries']} tries in {details['elapsed']:.1f}s"
    )


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_tries=5,
    max_time=60,
    on_backoff=[log_attempt, log_backoff],
    on_giveup=log_giveup,
    on_success=log_success,
)
def comprehensive_retry():
    return requests.get("https://api.example.com/data")
```

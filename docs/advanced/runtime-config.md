# Runtime Configuration

Configure backoff behavior dynamically at runtime.

## Overview

Decorator parameters can accept callables that are evaluated at runtime, allowing dynamic configuration based on application state, environment variables, or configuration files.

## Basic Pattern

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


# Change configuration at runtime
Config.MAX_RETRIES = 10
```

## Environment Variables

```python
import os


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=lambda: int(os.getenv("RETRY_MAX_TRIES", "5")),
    max_time=lambda: int(os.getenv("RETRY_MAX_TIME", "60")),
)
def env_configured():
    pass
```

## Configuration Files

```python
import json


def load_config():
    with open("config.json") as f:
        return json.load(f)


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=lambda: load_config()["retry"]["max_tries"],
    max_time=lambda: load_config()["retry"]["max_time"],
)
def file_configured():
    pass
```

## Dynamic Wait Strategies

```python
def get_wait_gen():
    if app.config.get("fast_retry"):
        return backoff.constant
    return backoff.expo


@backoff.on_exception(lambda: get_wait_gen(), Exception)
def dynamic_wait():
    pass
```

## Application State

```python
class RateLimiter:
    def __init__(self):
        self.rate_limited = False

    def get_interval(self):
        return 10 if self.rate_limited else 1


rate_limiter = RateLimiter()


@backoff.on_predicate(backoff.constant, interval=lambda: rate_limiter.get_interval())
def adaptive_poll():
    return check_resource()
```

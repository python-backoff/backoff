# backoff

[![Build Status](https://github.com/python-backoff/backoff/actions/workflows/ci.yaml/badge.svg)](https://github.com/python-backoff/backoff/actions/workflows/ci.yaml)
[![PyPI Version](https://img.shields.io/pypi/v/python-backoff.svg)](https://pypi.python.org/pypi/python-backoff)
[![License](https://img.shields.io/github/license/python-backoff/backoff)](https://github.com/python-backoff/backoff/blob/main/LICENSE)

**Function decoration for backoff and retry**

This module provides function decorators which can be used to wrap a function such that it will be retried until some condition is met. It is meant to be of use when accessing unreliable resources with the potential for intermittent failures (network resources, external APIs, etc).

## Features

- **Simple decorators** - Easy-to-use `@backoff.on_exception` and `@backoff.on_predicate` decorators
- **Multiple wait strategies** - Exponential, fibonacci, constant, and runtime-configurable strategies
- **Flexible configuration** - Control retry limits with `max_time`, `max_tries`, and custom give-up conditions
- **Event handlers** - Hook into retry lifecycle with `on_success`, `on_backoff`, and `on_giveup` callbacks
- **Async support** - Full support for `asyncio` coroutines
- **Type hints** - Fully typed for better IDE support
- **Battle-tested** - Used in production by thousands of projects

## Quick Start

Install via pip:

```bash
pip install python-backoff
```

Basic retry on exception:

```python
import requests

import backoff


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_time=60,
)
def get_url(url):
    return requests.get(url)
```

This will retry the function with exponential backoff whenever a `RequestException` is raised, giving up after 60 seconds.

## Common Use Cases

- [HTTP/API Calls](examples.md#httpapi-calls)
- [Database Operations](examples.md#database-operations)
- [Polling for Results](examples.md#polling-and-resource-waiting)

## Next Steps

- [Getting Started Guide](getting-started.md) - Detailed tutorial
- [User Guide](user-guide/decorators.md) - Complete reference
- [Examples](examples.md) - Real-world patterns
- [API Reference](api/reference.md) - Full API documentation

## Project Links

- [GitHub Repository](https://github.com/python-backoff/backoff)
- [PyPI Package](https://pypi.org/project/python-backoff/)
- [Issue Tracker](https://github.com/python-backoff/backoff/issues)
- [Changelog](changelog.md)

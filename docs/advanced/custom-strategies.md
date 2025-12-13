# Custom Wait Strategies

Create custom wait generators for specialized retry patterns.

## Wait Generator Interface

A wait generator is a function that yields wait times in seconds:

```python
def my_wait_gen():
    """Yields: 1, 2, 3, 4, 5, 5, 5, ..."""
    # Note: Using `yield from` can be unsafe in backoff wait generators.
    for i in range(1, 6):
        yield i
    while True:
        yield 5


@backoff.on_exception(my_wait_gen, Exception)
def my_function():
    pass
```

## Parameters

Accept parameters to customize behavior:

```python
def linear_backoff(start=1, increment=1, max_value=None):
    """Linear backoff: start, start+increment, start+2*increment, ..."""
    value = start
    while True:
        if max_value and value > max_value:
            yield max_value
        else:
            yield value
            value += increment


@backoff.on_exception(
    linear_backoff,
    Exception,
    start=2,
    increment=3,
    max_value=30,
)
def my_function():
    pass
```

## Examples

### Polynomial Backoff

```python
def polynomial_backoff(base=2, exponent=2, max_value=None):
    """Polynomial: base^(tries^exponent)"""
    n = 1
    while True:
        value = base ** (n**exponent)
        if max_value and value > max_value:
            yield max_value
        else:
            yield value
        n += 1


@backoff.on_exception(
    polynomial_backoff,
    Exception,
    base=2,
    exponent=1.5,
)
def my_function():
    pass
```

### Stepped Backoff

```python
def stepped_backoff(steps):
    """Different wait times for different ranges
    steps = [(3, 1), (5, 5), (None, 10)]  # 3 tries at 1s, next 5 at 5s, rest at 10s
    """
    for max_tries, wait_time in steps:
        if max_tries is None:
            while True:
                yield wait_time
        else:
            for _ in range(max_tries):
                yield wait_time


@backoff.on_exception(
    stepped_backoff,
    Exception,
    steps=[(3, 1), (3, 5), (None, 30)],
)
def my_function():
    pass
```

### Random Backoff

```python
import random


def random_backoff(min_wait=1, max_wait=60):
    """Random wait between min and max"""
    while True:
        yield random.uniform(min_wait, max_wait)


@backoff.on_exception(
    random_backoff,
    Exception,
    min_wait=1,
    max_wait=10,
)
def my_function():
    pass
```

### Time-of-Day Aware

```python
from datetime import datetime


def business_hours_backoff():
    """Shorter waits during business hours"""
    while True:
        hour = datetime.now().hour
        if 9 <= hour < 17:
            yield 5  # 5 seconds during business hours
        else:
            yield 60  # 1 minute otherwise


@backoff.on_exception(business_hours_backoff, Exception)
def my_function():
    pass
```

# Context Manager

Backoff provides a context manager generator for non-decorator usage.

## Basic Usage

```python
import random

import backoff

for attempt in backoff.retry_context():
    with attempt:
        choice = random.choice("Lorem ipsum dolor sit amet")
        if choice not in "aeiou":
            raise RuntimeError(f"Ah, no luck! (choice={choice})")
        else:
            print(f"Got it (choice={choice})")
```

`attempt` is an instance of `backoff.Attempt`, so a helper that
accepts one (e.g. for logging) can be typed against it directly:

```python
from backoff import Attempt


def log_attempt(attempt: Attempt) -> None:
    print(f"exception so far: {attempt.exception}")


for attempt in backoff.retry_context():
    with attempt:
        log_attempt(attempt)
        # ...
```

Handlers passed as `on_try`/`on_success`/`on_backoff`/`on_giveup` receive a
`dict` typed as `backoff.types.ContextDetails`:

```python
from backoff.types import ContextDetails


def log_backoff(details: ContextDetails) -> None:
    print(f"retrying in {details['wait']}s after {details.get('exception')}")


for attempt in backoff.retry_context(on_backoff=log_backoff):
    with attempt:
        ...
```

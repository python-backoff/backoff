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

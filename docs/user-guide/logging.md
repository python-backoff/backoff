# Logging

Configure logging for backoff retry events.

## Default Logger

Backoff uses the `'backoff'` logger by default. It's configured with a `NullHandler`, so nothing is output unless you configure it.

### Basic Setup

```python
import logging

# Enable backoff logging
logging.getLogger("backoff").addHandler(logging.StreamHandler())
logging.getLogger("backoff").setLevel(logging.INFO)
```

### Log Levels

- **INFO** - Logs all retry attempts
- **ERROR** - Logs only when giving up
- **WARNING** - Custom level for important retries
- **DEBUG** - Detailed information

```python
# Only log when giving up
logging.getLogger("backoff").setLevel(logging.ERROR)

# Log all retries
logging.getLogger("backoff").setLevel(logging.INFO)
```

## Custom Logger

Specify a custom logger by name or instance.

### Logger by Name

```python
@backoff.on_exception(backoff.expo, Exception, logger="my_custom_logger")
def my_function():
    pass
```

### Logger Instance

```python
import logging

my_logger = logging.getLogger("my_app.retries")
my_logger.addHandler(logging.FileHandler("retries.log"))
my_logger.setLevel(logging.WARNING)


@backoff.on_exception(backoff.expo, Exception, logger=my_logger)
def my_function():
    pass
```

## Disable Logging

Pass `logger=None` to disable all default logging:

```python
@backoff.on_exception(backoff.expo, Exception, logger=None)
def my_function():
    pass
```

Use with custom event handlers for complete control:

```python
def my_custom_log(details):
    print(f"Custom log: {details}")


@backoff.on_exception(
    backoff.expo, Exception, logger=None, on_backoff=my_custom_log
)
def my_function():
    pass
```

## Formatting

### Basic Format

```python
import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logging.getLogger("backoff").addHandler(logging.StreamHandler())
```

### Structured Logging (JSON)

```python
import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(log_data)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())

backoff_logger = logging.getLogger("backoff")
backoff_logger.addHandler(handler)
backoff_logger.setLevel(logging.INFO)
```

## Multiple Handlers

Send logs to multiple destinations:

```python
import logging

backoff_logger = logging.getLogger("backoff")

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)

# File handler
file_handler = logging.FileHandler("backoff.log")
file_handler.setLevel(logging.INFO)

# Add both handlers
backoff_logger.addHandler(console_handler)
backoff_logger.addHandler(file_handler)
backoff_logger.setLevel(logging.INFO)
```

## Per-Function Logging

Use different loggers for different functions:

```python
critical_logger = logging.getLogger("critical_ops")
routine_logger = logging.getLogger("routine_ops")


@backoff.on_exception(
    backoff.expo,
    Exception,
    logger=critical_logger,
    max_tries=10,
)
def critical_operation():
    pass


@backoff.on_exception(
    backoff.expo,
    Exception,
    logger=routine_logger,
    max_tries=3,
)
def routine_operation():
    pass
```

## Complete Example

```python
import logging
from logging.handlers import RotatingFileHandler

# Create custom logger
logger = logging.getLogger("myapp.backoff")
logger.setLevel(logging.INFO)

# Console handler with WARNING level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_format = logging.Formatter("%(levelname)s: %(message)s")
console_handler.setFormatter(console_format)

# File handler with INFO level and rotation
file_handler = RotatingFileHandler(
    "backoff.log",
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
)
file_handler.setLevel(logging.INFO)
file_format = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
file_handler.setFormatter(file_format)

# Add handlers
logger.addHandler(console_handler)
logger.addHandler(file_handler)


# Use in decorator
@backoff.on_exception(backoff.expo, Exception, logger=logger, max_tries=5)
def my_function():
    pass
```

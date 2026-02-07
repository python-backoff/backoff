# Examples

Real-world examples of using backoff in production.

## HTTP/API Calls

### Basic API Retry

```python
import requests

import backoff


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_time=60,
)
def fetch_data(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()
```

### Rate Limiting with Retry-After

```python
@backoff.on_predicate(
    backoff.runtime,
    predicate=lambda r: r.status_code == 429,
    value=lambda r: int(r.headers.get("Retry-After", 1)),
    jitter=None,
    max_tries=10,
)
def rate_limited_api_call(endpoint):
    return requests.get(endpoint)
```

### Conditional Retry on Status Codes

```python
def should_retry(response):
    # Retry on 5xx and 429, but not 4xx
    return response.status_code >= 500 or response.status_code == 429


@backoff.on_predicate(
    backoff.expo,
    should_retry,
    max_time=120,
)
def resilient_api_call(url):
    response = requests.get(url)
    if 400 <= response.status_code < 500 and response.status_code != 429:
        response.raise_for_status()  # Don't retry client errors
    return response
```

## Database Operations

### Connection Retry

```python
import sqlalchemy
from sqlalchemy.exc import OperationalError, TimeoutError


@backoff.on_exception(
    backoff.expo,
    (OperationalError, TimeoutError),
    max_tries=5,
    max_time=30,
)
def connect_to_database(connection_string):
    engine = sqlalchemy.create_engine(connection_string)
    return engine.connect()
```

### Transaction Retry with Deadlock Handling

```python
from sqlalchemy.exc import DBAPIError


def is_deadlock(e):
    """Check if exception is a deadlock"""
    if isinstance(e, DBAPIError):
        return "deadlock" in str(e).lower()
    return False


@backoff.on_exception(
    backoff.expo,
    DBAPIError,
    giveup=lambda e: not is_deadlock(e),
    max_tries=3,
)
def execute_transaction(session, operation):
    try:
        result = operation(session)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
```

## Async/Await

### Async HTTP Client

```python
import aiohttp

import backoff


@backoff.on_exception(
    backoff.expo,
    aiohttp.ClientError,
    max_time=60,
)
async def fetch_async(url):
    async with aiohttp.ClientSession() as session, session.get(url) as response:
        return await response.json()
```

### Async Database Operations

```python
import asyncpg


@backoff.on_exception(
    backoff.expo,
    asyncpg.PostgresError,
    max_tries=5,
)
async def query_async(pool, query):
    async with pool.acquire() as conn:
        return await conn.fetch(query)
```

### Multiple Async Tasks with Individual Retries

```python
@backoff.on_exception(
    backoff.expo,
    aiohttp.ClientError,
    max_tries=3,
)
async def fetch_with_retry(session, url):
    async with session.get(url) as response:
        return await response.json()


async def fetch_all(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_with_retry(session, url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

## Polling and Resource Waiting

### Poll for Job Completion

```python
@backoff.on_predicate(
    backoff.constant,
    lambda job: job["status"] != "complete",
    interval=5,
    max_time=600,
)
def wait_for_job(job_id):
    response = requests.get(f"/api/jobs/{job_id}")
    return response.json()
```

### Wait for Resource Availability

```python
@backoff.on_predicate(
    backoff.fibo,
    lambda result: not result,
    max_value=30,
    max_time=300,
)
def wait_for_resource(resource_id):
    try:
        resource = get_resource(resource_id)
        return resource if resource.is_ready() else None
    except ResourceNotFound:
        return None
```

### Message Queue Polling

```python
@backoff.on_predicate(
    backoff.constant,
    lambda messages: len(messages) == 0,
    interval=2,
    jitter=None,
)
def poll_queue(queue_name):
    return message_queue.receive(queue_name, max_messages=10)
```

## Cloud Services

### AWS S3 Operations

```python
import boto3
from botocore.exceptions import ClientError


def is_throttled(e):
    if isinstance(e, ClientError):
        return e.response["Error"]["Code"] in ["SlowDown", "RequestLimitExceeded"]
    return False


@backoff.on_exception(
    backoff.expo,
    ClientError,
    giveup=lambda e: not is_throttled(e),
    max_tries=5,
)
def upload_to_s3(bucket, key, data):
    s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=data)
```

### DynamoDB with Exponential Backoff

```python
@backoff.on_exception(
    backoff.expo,
    ClientError,
    giveup=lambda e: (
        e.response["Error"]["Code"] != "ProvisionedThroughputExceededException"
    ),
    max_time=30,
)
def write_to_dynamodb(table_name, item):
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    table.put_item(Item=item)
```

## Testing and Debugging

### Logging Retry Events

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def log_retry(details):
    logger.warning(
        f"Backing off {details['wait']:.1f}s after {details['tries']} tries "
        f"calling {details['target'].__name__}"
    )


def log_giveup(details):
    logger.error(
        f"Giving up after {details['tries']} tries and {details['elapsed']:.1f}s"
    )


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=log_retry,
    on_giveup=log_giveup,
    max_tries=5,
)
def flaky_function():
    pass
```

### Metrics Collection

```python
retry_metrics = {"total_retries": 0, "giveups": 0}


def count_retry(details):
    retry_metrics["total_retries"] += 1


def count_giveup(details):
    retry_metrics["giveups"] += 1


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_backoff=count_retry,
    on_giveup=count_giveup,
    max_tries=3,
)
def monitored_function():
    pass
```

## Advanced Patterns

### Combining Multiple Decorators

```python
# Separate retry logic for different failure modes
@backoff.on_predicate(
    backoff.fibo,
    lambda result: result is None,
    max_value=13,
)
@backoff.on_exception(
    backoff.expo,
    requests.exceptions.HTTPError,
    giveup=lambda e: 400 <= e.response.status_code < 500,
    max_time=60,
)
@backoff.on_exception(
    backoff.expo,
    requests.exceptions.Timeout,
    max_tries=3,
)
def comprehensive_retry(url):
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    return data if data.get("ready") else None
```

### Circuit Breaker Pattern

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.opened_at = None

    def should_attempt(self):
        if self.opened_at is None:
            return True
        if time.time() - self.opened_at > self.timeout:
            self.opened_at = None
            self.failure_count = 0
            return True
        return False

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.opened_at = time.time()


circuit_breaker = CircuitBreaker()


def check_circuit(e):
    circuit_breaker.record_failure()
    return not circuit_breaker.should_attempt()


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    giveup=check_circuit,
    max_tries=5,
)
def protected_api_call(url):
    if not circuit_breaker.should_attempt():
        raise Exception("Circuit breaker is open")
    return requests.get(url)
```

### Dynamic Configuration

```python
class RetryConfig:
    def __init__(self):
        self.max_time = 60
        self.max_tries = 5

    def get_max_time(self):
        return self.max_time

    def get_max_tries(self):
        return self.max_tries


config = RetryConfig()


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_time=lambda: config.get_max_time(),
    max_tries=lambda: config.get_max_tries(),
)
def configurable_retry():
    pass


# Can update config at runtime
config.max_time = 120
```

## Error Handling

### Graceful Degradation

```python
@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_tries=3,
    raise_on_giveup=False,
)
def optional_api_call(url):
    return requests.get(url)


# Use with fallback
result = optional_api_call(primary_url)
if result is None:
    result = get_from_cache()
```

### Custom Exception on Giveup

```python
class RetryExhaustedError(Exception):
    pass


def raise_custom_error(details):
    raise RetryExhaustedError(f"Failed after {details['tries']} attempts")


@backoff.on_exception(
    backoff.expo,
    Exception,
    on_giveup=raise_custom_error,
    max_tries=5,
    raise_on_giveup=False,
)
def critical_operation():
    pass
```

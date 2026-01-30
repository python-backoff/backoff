import backoff
import requests


@backoff.on_predicate(
    backoff.runtime,
    predicate=lambda r: r.status_code == 429,
    value=lambda r: int(r.headers.get("Retry-After", 1)),
    jitter=None,
    max_tries=10,
)
def rate_limited_api_call(endpoint):
    return requests.get(endpoint)

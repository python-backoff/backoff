import backoff
import requests


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

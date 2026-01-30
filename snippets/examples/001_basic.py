import backoff
import requests


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_time=60,
)
def fetch_data(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

"""Integration tests

Higher-level tests integrating with 3rd party modules using iodiomatic
backoff patterns.
"""

from types import SimpleNamespace
from unittest.mock import patch

import requests
import responses
from requests import HTTPError

import backoff
import backoff._sync


@responses.activate
def test_on_predicate_runtime() -> None:
    log = []

    def sleep(seconds: float) -> None:
        log.append(seconds)

    url = "http://example.com"

    responses.add(responses.GET, url, status=429, headers={"Retry-After": "1"})
    responses.add(responses.GET, url, status=429, headers={"Retry-After": "3"})
    responses.add(responses.GET, url, status=429, headers={"Retry-After": "7"})
    responses.add(responses.GET, url, status=200)

    @backoff.on_predicate(
        backoff.runtime,
        predicate=lambda r: r.status_code == 429,
        value=lambda r: int(r.headers.get("Retry-After")),
        jitter=None,
    )
    def get_url() -> requests.Response:
        return requests.get(url)

    with patch.object(backoff._sync, "time", SimpleNamespace(sleep=sleep)):
        resp = get_url()

    assert resp.status_code == 200

    assert log == [1, 3, 7]


@responses.activate
def test_on_exception_runtime() -> None:
    log = []

    def sleep(seconds: float) -> None:
        log.append(seconds)

    url = "http://example.com"

    responses.add(responses.GET, url, status=429, headers={"Retry-After": "1"})
    responses.add(responses.GET, url, status=429, headers={"Retry-After": "3"})
    responses.add(responses.GET, url, status=429, headers={"Retry-After": "7"})
    responses.add(responses.GET, url, status=200)

    @backoff.on_exception(
        backoff.runtime,
        HTTPError,
        value=lambda e: int(e.response.headers.get("Retry-After")),
        jitter=None,
    )
    def get_url() -> requests.Response:
        resp = requests.get(url)
        resp.raise_for_status()
        return resp

    with patch.object(backoff._sync, "time", SimpleNamespace(sleep=sleep)):
        resp = get_url()

    assert resp.status_code == 200

    assert log == [1, 3, 7]

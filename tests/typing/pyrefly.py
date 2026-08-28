from typing_extensions import assert_type

import backoff


@backoff.on_exception(backoff.expo, ValueError)
def fetch_with_exception(value: str) -> str:
    return value


@backoff.on_predicate(backoff.expo)
def fetch_with_predicate(value: str) -> str:
    return value


def consume_sync_results() -> str:
    exception_result = fetch_with_exception("exception")
    assert_type(exception_result, str)
    predicate_result = fetch_with_predicate("predicate")
    assert_type(predicate_result, str)
    return exception_result.upper() + predicate_result.upper()

import backoff


@backoff.on_exception(backoff.expo, ValueError)
def fetch_with_exception(value: str):
    return value


@backoff.on_predicate(backoff.expo)
def fetch_with_predicate(value: str):
    return value


def consume_sync_results() -> str:
    exception_result = fetch_with_exception("exception")
    predicate_result = fetch_with_predicate("predicate")
    return exception_result.upper() + predicate_result.upper()

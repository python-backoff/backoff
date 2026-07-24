import backoff


def test_full_jitter() -> None:
    for input in range(100):
        for _i in range(100):
            jitter = backoff.full_jitter(input)
        assert jitter >= 0
        assert jitter <= input

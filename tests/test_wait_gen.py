# ruff: file-ignore[float-equality-comparison]

import math

import backoff


def test_decay() -> None:
    gen = backoff.decay()
    gen.send(None)
    for i in range(10):
        assert math.e**-i == next(gen)


def test_decay_init100() -> None:
    gen = backoff.decay(initial_value=100)
    gen.send(None)
    for i in range(10):
        assert 100 * math.e**-i == next(gen)


def test_decay_init100_decay3() -> None:
    gen = backoff.decay(initial_value=100, decay_factor=3)
    gen.send(None)
    for i in range(10):
        assert 100 * math.e ** (-i * 3) == next(gen)


def test_decay_init100_decay3_min5() -> None:
    gen = backoff.decay(initial_value=100, decay_factor=3, min_value=5)
    gen.send(None)
    for i in range(10):
        assert max(100 * math.e ** (-i * 3), 5) == next(gen)


def test_expo() -> None:
    gen = backoff.expo()
    gen.send(None)
    for i in range(9):
        assert 2**i == next(gen)


def test_expo_base3() -> None:
    gen = backoff.expo(base=3)
    gen.send(None)
    for i in range(9):
        assert 3**i == next(gen)


def test_expo_factor3() -> None:
    gen = backoff.expo(factor=3)
    gen.send(None)
    for i in range(9):
        assert 3 * 2**i == next(gen)


def test_expo_base3_factor5() -> None:
    gen = backoff.expo(base=3, factor=5)
    gen.send(None)
    for i in range(9):
        assert 5 * 3**i == next(gen)


def test_expo_max_value() -> None:
    gen = backoff.expo(max_value=2**4)
    gen.send(None)
    expected = [1, 2, 4, 8, 16, 16, 16]
    for expect in expected:
        assert expect == next(gen)


def test_expo_max_value_factor() -> None:
    gen = backoff.expo(factor=3, max_value=2**4)
    gen.send(None)
    expected = [3 * 1, 3 * 2, 3 * 4, 16, 16, 16, 16]
    for expect in expected:
        assert expect == next(gen)


def test_fibo() -> None:
    gen = backoff.fibo()
    gen.send(None)
    expected = [1, 1, 2, 3, 5, 8, 13]
    for expect in expected:
        assert expect == next(gen)


def test_fibo_max_value() -> None:
    gen = backoff.fibo(max_value=8)
    gen.send(None)
    expected = [1, 1, 2, 3, 5, 8, 8, 8]
    for expect in expected:
        assert expect == next(gen)


def test_constant() -> None:
    gen = backoff.constant(interval=3)
    gen.send(None)
    for _i in range(9):
        assert next(gen) == 3

    gen = backoff.constant(interval=[1, 2.0, 3.25])
    gen.send(None)
    assert next(gen) == 1
    assert next(gen) == 2.0
    assert next(gen) == 3.25
    assert next(gen, None) is None


def test_runtime() -> None:
    gen = backoff.runtime(value=lambda x: x)
    gen.send(None)
    for i in range(20):
        assert i == gen.send(i)

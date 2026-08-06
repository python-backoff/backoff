from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import backoff

if TYPE_CHECKING:
    from backoff._typing import ContextDetails


def test_retry_context_success_after_failures() -> None:
    calls = []

    for attempt in backoff.retry_context(
        ValueError,
        backoff.constant,
        interval=0,
        max_tries=5,
        jitter=None,
    ):
        with attempt:
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("nope")

    assert len(calls) == 3


def test_retry_context_giveup_raises() -> None:
    calls = []

    def run() -> None:
        for attempt in backoff.retry_context(
            ValueError,
            backoff.constant,
            interval=0,
            max_tries=3,
            jitter=None,
        ):
            with attempt:
                calls.append(1)
                raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        run()

    assert len(calls) == 3


def test_retry_context_giveup_no_raise() -> None:
    calls = []

    for attempt in backoff.retry_context(
        ValueError,
        backoff.constant,
        interval=0,
        max_tries=3,
        jitter=None,
        raise_on_giveup=False,
    ):
        with attempt:
            calls.append(1)
            raise ValueError("always fails")

    assert len(calls) == 3


def test_retry_context_unmatched_exception_propagates_immediately() -> None:
    calls = []

    def run() -> None:
        for attempt in backoff.retry_context(
            ValueError,
            backoff.constant,
            interval=0,
            max_tries=5,
            jitter=None,
        ):
            with attempt:
                calls.append(1)
                raise KeyError("wrong type")

    with pytest.raises(KeyError, match="wrong type"):
        run()

    assert len(calls) == 1


def test_retry_context_giveup_predicate() -> None:
    calls = []

    def run() -> None:
        for attempt in backoff.retry_context(
            ValueError,
            backoff.constant,
            interval=0,
            max_tries=5,
            jitter=None,
            giveup=lambda e: True,
        ):
            with attempt:
                calls.append(1)
                raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        run()

    assert len(calls) == 1


def test_retry_context_handlers() -> None:
    backoffs: list[ContextDetails] = []
    giveups: list[ContextDetails] = []
    successes: list[ContextDetails] = []

    for attempt in backoff.retry_context(
        ValueError,
        backoff.constant,
        interval=0,
        max_tries=3,
        jitter=None,
        on_backoff=backoffs.append,
        on_giveup=giveups.append,
        on_success=successes.append,
    ):
        with attempt:
            if len(backoffs) < 2:
                raise ValueError("nope")

    assert len(backoffs) == 2
    assert len(giveups) == 0
    assert len(successes) == 1
    assert backoffs[0]["tries"] == 1
    assert isinstance(backoffs[0].get("exception"), ValueError)


def test_retry_context_wait_gen_exhausted() -> None:
    calls = []
    giveups: list[ContextDetails] = []

    def run() -> None:
        for attempt in backoff.retry_context(
            ValueError,
            backoff.constant,
            interval=(0,),
            jitter=None,
            on_giveup=giveups.append,
        ):
            with attempt:
                calls.append(1)
                raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        run()

    assert len(calls) == 2
    assert len(giveups) == 1
    assert isinstance(giveups[0].get("exception"), ValueError)


def test_retry_context_wait_gen_exhausted_always_raises() -> None:
    calls = []
    giveups: list[ContextDetails] = []

    def run() -> None:
        for attempt in backoff.retry_context(
            ValueError,
            backoff.constant,
            interval=(0,),
            jitter=None,
            on_giveup=giveups.append,
            raise_on_giveup=False,
        ):
            with attempt:
                calls.append(1)
                raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        run()

    assert len(calls) == 2
    assert len(giveups) == 1
    assert isinstance(giveups[0].get("exception"), ValueError)


@pytest.mark.asyncio
async def test_aretry_context_success_after_failures() -> None:
    calls = []

    async for attempt in backoff.aretry_context(
        ValueError,
        backoff.constant,
        interval=0,
        max_tries=5,
        jitter=None,
    ):
        with attempt:
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("nope")

    assert len(calls) == 3


@pytest.mark.asyncio
async def test_aretry_context_giveup_raises() -> None:
    calls = []

    async def run() -> None:
        async for attempt in backoff.aretry_context(
            ValueError,
            backoff.constant,
            interval=0,
            max_tries=3,
            jitter=None,
        ):
            with attempt:
                calls.append(1)
                raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        await run()

    assert len(calls) == 3


@pytest.mark.asyncio
async def test_aretry_context_async_giveup_predicate() -> None:
    calls = []

    async def agiveup(exc: BaseException) -> bool:
        return True

    async def run() -> None:
        async for attempt in backoff.aretry_context(
            ValueError,
            backoff.constant,
            interval=0,
            max_tries=5,
            jitter=None,
            giveup=agiveup,
        ):
            with attempt:
                calls.append(1)
                raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        await run()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_aretry_context_async_handlers() -> None:
    backoffs = []

    async def on_backoff(details) -> None:
        backoffs.append(details)

    calls = []
    async for attempt in backoff.aretry_context(
        ValueError,
        backoff.constant,
        interval=0,
        max_tries=5,
        jitter=None,
        on_backoff=on_backoff,
    ):
        with attempt:
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("nope")

    assert len(backoffs) == 2
    assert backoffs[0]["tries"] == 1
    assert isinstance(backoffs[0]["exception"], ValueError)


@pytest.mark.asyncio
async def test_aretry_context_async_giveup_no_raise() -> None:
    calls = []

    async for attempt in backoff.aretry_context(
        ValueError,
        backoff.constant,
        interval=0,
        max_tries=3,
        jitter=None,
        raise_on_giveup=False,
    ):
        with attempt:
            calls.append(1)
            raise ValueError("always fails")

    assert len(calls) == 3


@pytest.mark.asyncio
async def test_aretry_context_wait_gen_exhausted() -> None:
    calls = []
    giveups: list[ContextDetails] = []

    async def run() -> None:
        async for attempt in backoff.aretry_context(
            ValueError,
            backoff.constant,
            interval=(0,),
            jitter=None,
            on_giveup=giveups.append,
        ):
            with attempt:
                calls.append(1)
                raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        await run()

    assert len(calls) == 2
    assert len(giveups) == 1
    assert isinstance(giveups[0].get("exception"), ValueError)


@pytest.mark.asyncio
async def test_aretry_context_wait_gen_exhausted_always_raises() -> None:
    calls = []
    giveups: list[ContextDetails] = []

    async def run() -> None:
        async for attempt in backoff.aretry_context(
            ValueError,
            backoff.constant,
            interval=(0,),
            jitter=None,
            on_giveup=giveups.append,
            raise_on_giveup=False,
        ):
            with attempt:
                calls.append(1)
                raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        await run()

    assert len(calls) == 2
    assert len(giveups) == 1
    assert isinstance(giveups[0].get("exception"), ValueError)

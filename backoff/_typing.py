from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine, Generator
from typing import Any, TypeAlias, TypedDict, TypeVar


class _BaseDetails(TypedDict):
    target: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    tries: int
    elapsed: float


class _CallDetails(TypedDict, total=False):
    wait: float  # present in the on_backoff handler case for either decorator
    value: Any  # present in the on_predicate decorator case
    exception: Exception  # present in the on_exception decorator case


class Details(_BaseDetails, _CallDetails, total=False):
    pass


class _BaseContextDetails(TypedDict):
    tries: int
    elapsed: float


class _ContextCallDetails(TypedDict, total=False):
    wait: float  # present in the on_backoff handler case
    value: Any  # present in the on_predicate decorator case
    exception: Exception  # present in the on_giveup handler case


class ContextDetails(_BaseContextDetails, _ContextCallDetails, total=False):
    """Details passed to handlers registered with `retry_context`/`aretry_context`.

    Unlike `Details`, there's no wrapped callable, so no `target`/`args`/`kwargs`.
    """


T = TypeVar("T")

_AnyLogger = logging.Logger | logging.LoggerAdapter  # type: ignore[type-arg]
_AnyLoggerOrName = str | _AnyLogger
_CallableT = TypeVar("_CallableT", bound=Callable[..., Any])  # ruff:ignore[unused-private-type-var]
_ContextHandler = (
    Callable[[ContextDetails], None]
    | Callable[[ContextDetails], Coroutine[Any, Any, None]]
)
_Handler = Callable[[Details], None] | Callable[[Details], Coroutine[Any, Any, None]]
_Jitterer = Callable[[float], float]
_MaybeCallable: TypeAlias = T | Callable[[], T]  # ruff: ignore[unused-private-type-alias]
_MaybeTuple: TypeAlias = T | tuple[T, ...]  # ruff: ignore[unused-private-type-alias]
_Predicate = Callable[[T], bool] | Callable[[T], Coroutine[Any, Any, bool]]
_WaitGenerator = Callable[..., Generator[float, Any, None]]

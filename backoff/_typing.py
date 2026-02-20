from __future__ import annotations

import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Generator,
    Sequence,
    TypedDict,
    TypeVar,
    Union,
)

if TYPE_CHECKING:
    from types import FunctionType


class _Details(TypedDict):
    target: FunctionType
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    tries: int
    elapsed: float


class Details(_Details, total=False):
    wait: float  # present in the on_backoff handler case for either decorator
    value: Any  # present in the on_predicate decorator case
    exception: Exception  # present in the on_exception decorator case


T = TypeVar("T")

_CallableT = TypeVar("_CallableT", bound=Callable[..., Any])  # noqa: PYI018
_Handler = Union[
    Callable[[Details], None],
    Callable[[Details], Coroutine[Any, Any, None]],
]
_Jitterer = Callable[[float], float]
_MaybeCallable = Union[T, Callable[[], T]]
_MaybeLogger = Union[str, logging.Logger, logging.LoggerAdapter, None]
_MaybeSequence = Union[T, Sequence[T]]
_Predicate = Callable[[T], bool]
_WaitGenerator = Callable[..., Generator[float, None, None]]

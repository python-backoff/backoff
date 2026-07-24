from __future__ import annotations

import collections
import functools
from typing import TYPE_CHECKING, Callable, TypeVar

if TYPE_CHECKING:
    import sys

    if sys.version_info >= (3, 10):
        from typing import ParamSpec
    else:
        from typing_extensions import ParamSpec

    T = TypeVar("T")
    P = ParamSpec("P")


# create event handler which log their invocations to a dict
def _log_hdlrs():
    log = collections.defaultdict(list)

    def log_hdlr(event, details):
        log[event].append(details)

    log_success = functools.partial(log_hdlr, "success")
    log_backoff = functools.partial(log_hdlr, "backoff")
    log_giveup = functools.partial(log_hdlr, "giveup")

    return log, log_success, log_backoff, log_giveup


# decorator that that saves the target as
# an attribute of the decorated function
def _save_target(f: Callable[P, T]) -> Callable[P, T]:
    f._target = f  # type: ignore[attr-defined] # ty:ignore[unresolved-attribute]
    return f

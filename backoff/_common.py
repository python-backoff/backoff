from __future__ import annotations

import functools
import logging
import sys
import traceback
import warnings
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable
    from typing import Protocol

    from backoff._typing import (
        Details,
        _Handler,
        _Jitterer,
        _MaybeCallable,
        _WaitGenerator,
    )

    class _DefaultHandler(Protocol):
        def __call__(
            self,
            details: Details,
            *,
            logger: logging.Logger | logging.LoggerAdapter,
            log_level: int,
        ) -> None: ...


# Use module-specific logger with a default null handler.
_logger = logging.getLogger("backoff")
_logger.addHandler(logging.NullHandler())  # pragma: no cover
_logger.setLevel(logging.INFO)

T = TypeVar("T")


# Evaluate arg that can be either a fixed value or a callable.
def _maybe_call(f: _MaybeCallable[T] | None, *args: Any, **kwargs: Any) -> T | None:
    if callable(f):
        try:
            return f(*args, **kwargs)  # ty:ignore[call-top-callable, invalid-return-type]
        except TypeError:
            return f  # type: ignore[return-value] # ty:ignore[invalid-return-type]
    else:
        return f


def _init_wait_gen(
    wait_gen: _WaitGenerator,
    wait_gen_kwargs: dict[str, Any],
) -> Generator[Any, Any, None]:
    kwargs = {k: _maybe_call(v) for k, v in wait_gen_kwargs.items()}
    initialized = wait_gen(**kwargs)
    initialized.send(None)  # Initialize with an empty send
    return initialized


def _next_wait(
    wait: Generator[float, int | None, None],
    send_value: Any,
    jitter: _Jitterer | None,
    elapsed: float,
    max_time: float | None,
) -> float:
    value = wait.send(send_value)
    try:
        seconds = jitter(value) if jitter is not None else value
    except TypeError:
        warnings.warn(
            "Nullary jitter function signature is deprecated. Use "
            "unary signature accepting a wait value in seconds and "
            "returning a jittered version of it.",
            DeprecationWarning,
            stacklevel=2,
        )

        seconds = value + jitter()  # type: ignore[call-arg, misc] # ty:ignore[missing-argument, call-non-callable]

    # don't sleep longer than remaining allotted max_time
    if max_time is not None:
        seconds = min(seconds, max_time - elapsed)

    return seconds


def _prepare_logger(
    logger: str | logging.Logger | logging.LoggerAdapter | None,
) -> logging.Logger | logging.LoggerAdapter | None:
    if isinstance(logger, str):
        logger = logging.getLogger(logger)
    return logger


# Configure handler list with user specified handler and optionally
# with a default handler bound to the specified logger.
def _config_handlers(
    user_handlers: _Handler | Iterable[_Handler] | None,
    *,
    default_handler: _DefaultHandler | None = None,
    logger: logging.Logger | logging.LoggerAdapter | None = None,
    log_level: int | None = None,
) -> list[_Handler]:
    handlers: list[_Handler] = []
    if logger is not None:
        assert log_level is not None, "Log level is not specified"
        assert default_handler is not None, "Default handler is not specified"
        # bind the specified logger to the default log handler
        log_handler = functools.partial(
            default_handler,
            logger=logger,
            log_level=log_level,
        )
        handlers.append(log_handler)

    if user_handlers is None:
        return handlers

    # user specified handlers can either be an iterable of handlers
    # or a single handler. either way append them to the list.
    if hasattr(user_handlers, "__iter__"):
        # add all handlers in the iterable
        # pyrefly: ignore [bad-argument-type]
        handlers += list(user_handlers)  # ty:ignore[invalid-argument-type]
    else:
        # append a single handler
        # pyrefly: ignore [bad-argument-type]
        handlers.append(user_handlers)

    return handlers


# Default backoff handler
def _log_backoff(
    details: Details,
    logger: logging.Logger | logging.LoggerAdapter,
    log_level: int,
) -> None:
    msg = "Backing off %s(...) for %.1fs (%s)"
    log_args = [details["target"].__name__, details["wait"]]  # ty:ignore[unresolved-attribute]

    exc_typ, exc, _ = sys.exc_info()
    if exc is not None:
        exc_fmt = traceback.format_exception_only(exc_typ, exc)[-1]
        log_args.append(exc_fmt.rstrip("\n"))
    else:
        log_args.append(details["value"])
    logger.log(log_level, msg, *log_args)


# Default giveup handler
def _log_giveup(
    details: Details,
    logger: logging.Logger | logging.LoggerAdapter,
    log_level: int,
) -> None:
    msg = "Giving up %s(...) after %d tries (%s)"
    log_args = [details["target"].__name__, details["tries"]]  # ty:ignore[unresolved-attribute]

    exc_typ, exc, _ = sys.exc_info()
    if exc is not None:
        exc_fmt = traceback.format_exception_only(exc_typ, exc)[-1]
        log_args.append(exc_fmt.rstrip("\n"))
    else:
        log_args.append(details["value"])

    logger.log(log_level, msg, *log_args)

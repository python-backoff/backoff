from __future__ import annotations

import functools
import logging
import time
import traceback
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    import sys
    from collections.abc import Generator, Iterable

    from backoff._typing import (
        ContextDetails,
        Details,
        _ContextHandler,
        _Jitterer,
        _MaybeCallable,
        _WaitGenerator,
    )

    if sys.version_info >= (3, 11):
        from typing import Self
    else:
        from typing_extensions import Self


# Use module-specific logger with a default null handler.
_logger = logging.getLogger("backoff")
_logger.addHandler(logging.NullHandler())  # pragma: no cover
_logger.setLevel(logging.INFO)

T = TypeVar("T")
_HandlerT = TypeVar("_HandlerT")


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
) -> Generator[float, Any, None]:
    kwargs = {k: _maybe_call(v) for k, v in wait_gen_kwargs.items()}
    initialized = wait_gen(**kwargs)
    initialized.send(None)  # Initialize with an empty send
    return initialized


def _next_wait(
    wait: Generator[float, None, None],
    send_value: Any,
    jitter: _Jitterer | None,
    elapsed: float,
    max_time: float | None,
) -> float:
    value = wait.send(send_value)
    seconds = jitter(value) if jitter is not None else value

    # don't sleep longer than remaining allotted max_time
    if max_time is not None:
        seconds = min(seconds, max_time - elapsed)

    return seconds


class _RetryState:
    """Bookkeeping shared by the sync and async retry loops.

    Tracks try count and elapsed time, and owns the initialized wait
    generator, so `retry_predicate`/`retry_exception` only need to drive
    the call/check/sleep sequence around it.
    """

    __slots__ = (
        "elapsed",
        "max_time",
        "max_tries",
        "start",
        "tries",
        "wait",
    )

    def __init__(
        self,
        wait_gen: _WaitGenerator,
        wait_gen_kwargs: dict[str, Any],
        *,
        max_tries: _MaybeCallable[int] | None = None,
        max_time: _MaybeCallable[float] | None = None,
    ) -> None:
        self.tries = 0
        self.elapsed: float = 0
        self.start = time.monotonic()
        self.max_tries = _maybe_call(max_tries)
        self.max_time = _maybe_call(max_time)
        self.wait = _init_wait_gen(wait_gen, wait_gen_kwargs)

    def start_attempt(self) -> None:
        self.tries += 1

    def record_elapsed(self) -> float:
        self.elapsed = time.monotonic() - self.start
        return self.elapsed

    def exhausted(self) -> bool:
        max_tries_exceeded = self.tries == self.max_tries
        max_time_exceeded = self.max_time is not None and self.elapsed >= self.max_time
        return max_tries_exceeded or max_time_exceeded

    def next_wait(self, send_value: Any, jitter: _Jitterer | None) -> float:
        return _next_wait(self.wait, send_value, jitter, self.elapsed, self.max_time)


class _Attempt:
    """A single attempt yielded by `retry_context`/`aretry_context`.

    Used as `with attempt: ...`. Exceptions matching `exception_types` are
    caught here so the driving generator (not this object) decides whether
    to retry, sleep, or let the exception propagate; anything else, or no
    exception at all, is left for the `with` block's normal exit behavior.
    """

    __slots__ = (
        "exception",
        "exception_types",
    )

    def __init__(
        self,
        exception_types: type[Exception] | tuple[type[Exception], ...],
    ) -> None:
        self.exception_types = exception_types
        self.exception: BaseException | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool:
        if exc_type is None:
            # self.outcome = _Success()
            return False

        if not issubclass(exc_type, self.exception_types):
            return False  # not ours; propagate immediately

        self.exception = exc
        return True  # suppress for now; the driving generator decides next


def _dispatch_handlers(handlers: Iterable[_ContextHandler], **details: Any) -> None:
    for hdlr in handlers:
        hdlr(details)  # type: ignore[arg-type] # ty:ignore[invalid-argument-type]


def _prepare_logger(
    logger: str | logging.Logger | logging.LoggerAdapter | None,
) -> logging.Logger | logging.LoggerAdapter | None:
    if isinstance(logger, str):
        logger = logging.getLogger(logger)
    return logger


# Configure handler list with user specified handler and optionally
# with a default handler bound to the specified logger.
def _config_handlers(
    user_handlers: _HandlerT | Iterable[_HandlerT] | None,
    *,
    default_handler: Callable[..., None] | None = None,
    logger: logging.Logger | logging.LoggerAdapter | None = None,
    log_level: int | None = None,
) -> list[_HandlerT]:
    handlers: list[_HandlerT] = []
    if logger is not None:
        assert log_level is not None, "Log level is not specified"
        assert default_handler is not None, "Default handler is not specified"
        # bind the specified logger to the default log handler
        log_handler = functools.partial(
            default_handler,
            logger=logger,
            log_level=log_level,
        )
        handlers.append(log_handler)  # type: ignore[arg-type] # ty:ignore[invalid-argument-type]

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

    exc = details.get("exception")
    if exc is not None:
        exc_fmt = traceback.format_exception_only(type(exc), exc)[-1]
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

    exc = details.get("exception")
    if exc is not None:
        exc_fmt = traceback.format_exception_only(type(exc), exc)[-1]
        log_args.append(exc_fmt.rstrip("\n"))
    else:
        log_args.append(details["value"])

    logger.log(log_level, msg, *log_args)


# Default backoff handler for retry_context/aretry_context (no wrapped
# callable, so no name to log; the exception is read from `details`
# directly since it's no longer the active exception by this point).
def _log_backoff_context(
    details: ContextDetails,
    logger: logging.Logger | logging.LoggerAdapter,
    log_level: int,
) -> None:
    logger.log(
        log_level,
        "Backing off retry_context(...) for %.1fs (%s)",
        details["wait"],
        details.get("exception"),
    )


# Default giveup handler for retry_context/aretry_context.
def _log_giveup_context(
    details: ContextDetails,
    logger: logging.Logger | logging.LoggerAdapter,
    log_level: int,
) -> None:
    logger.log(
        log_level,
        "Giving up retry_context(...) after %d tries (%s)",
        details["tries"],
        details.get("exception"),
    )

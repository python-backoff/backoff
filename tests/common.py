from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import ParamSpec, TypeAlias

    from backoff._typing import Details

    Event: TypeAlias = Literal["backoff", "giveup", "success", "try"]
    Events: TypeAlias = dict[Event, list[Details]]

    T = TypeVar("T")
    P = ParamSpec("P")


# decorator that that saves the target as
# an attribute of the decorated function
def _save_target(f: Callable[P, T]) -> Callable[P, T]:
    f._target = f  # type: ignore[attr-defined] # ty:ignore[unresolved-attribute]
    return f


def _init_events() -> Events:
    return {
        "backoff": [],
        "giveup": [],
        "success": [],
        "try": [],
    }


@dataclass
class EventAppender:
    events: Events = field(default_factory=_init_events)

    def on_event(self, event: Event) -> Callable[[Details], None]:
        return self.events[event].append

    def counts(self) -> dict[Event, int]:
        return {k: len(v) for k, v in self.events.items()}

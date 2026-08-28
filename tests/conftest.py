from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import pytest

if TYPE_CHECKING:
    import sys

    from backoff._typing import Details

    if sys.version_info >= (3, 10):
        from typing import TypeAlias
    else:
        from typing_extensions import TypeAlias

    Event: TypeAlias = Literal["backoff", "giveup", "success"]


@dataclass
class EventAppender:
    events: dict[Event, list[Details]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def on_event(self, event: Event):
        return self.events[event].append

    def counts(self) -> dict[Event, int]:
        return {k: len(v) for k, v in self.events.items()}


@pytest.fixture
def appender() -> EventAppender:
    return EventAppender()

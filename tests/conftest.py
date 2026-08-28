from __future__ import annotations

import pytest

from tests.common import EventAppender


@pytest.fixture
def appender() -> EventAppender:
    return EventAppender()

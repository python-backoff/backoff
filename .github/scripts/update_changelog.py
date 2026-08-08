"""Prepend a published GitHub release's notes to CHANGELOG.md.

Run by .github/workflows/changelog.yaml on the `release: published` event.
Drops the leading `## Unreleased` section, if present, since it's
superseded by the version being inserted, then adds a `## [tag] - date`
section built from the release body right after the `# Changelog` title.
"""

from __future__ import annotations

import os
from pathlib import Path

CHANGELOG = Path("CHANGELOG.md")
UNRELEASED_HEADING = "## Unreleased"


def main() -> None:
    tag = os.environ["RELEASE_TAG"]
    date = os.environ["RELEASE_DATE"][:10]  # YYYY-MM-DD from an ISO 8601 timestamp
    body = os.environ["RELEASE_BODY"].strip()

    lines = CHANGELOG.read_text().splitlines(keepends=True)
    if lines[0].strip() != "# Changelog":
        msg = f"unexpected first line: {lines[0]!r}"
        raise ValueError(msg)

    # Skip blank lines right after the title.
    start = 1
    while start < len(lines) and not lines[start].strip():
        start += 1

    # Drop a leading "## Unreleased" section: its content is superseded by
    # the version we're about to insert.
    end = start
    if start < len(lines) and lines[start].strip() == UNRELEASED_HEADING:
        end = start + 1
        while end < len(lines) and not lines[end].startswith("## "):
            end += 1

    section = f"## [{tag}] - {date}\n\n{body}\n"
    new_lines = [*lines[:1], "\n", section, "\n", *lines[end:]]
    CHANGELOG.write_text("".join(new_lines))


if __name__ == "__main__":
    main()

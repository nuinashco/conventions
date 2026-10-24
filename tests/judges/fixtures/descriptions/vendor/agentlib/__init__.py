"""Stand-in for a third-party agent library, as installed in site-packages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompactionConfig:
    compaction_interval: int
    """The number of new user-initiated invocations that triggers a compaction."""


def compact(config: CompactionConfig) -> None:
    """Summarise the session's events every `config.compaction_interval` invocations."""

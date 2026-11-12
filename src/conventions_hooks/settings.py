"""The `[tool.conventions]` table that opts a repo in and turns checks off."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from attrs import frozen

RULE_ID = re.compile(r"[A-Z]+-\d+")
KEYS = frozenset({"ignore", "review"})


class SettingsError(Exception):
    """A `[tool.conventions]` table that does not parse as documented."""


@frozen
class Settings:
    """What a repo's `[tool.conventions]` table says; `enabled` when it has one.

    `review` is false when the table turns `review-comments` off, which leaves every
    other check on.
    """

    enabled: bool
    ignore: frozenset[str] = frozenset()
    review: bool = True

    @classmethod
    def of(cls, path: Path) -> Settings:
        """Return the settings of the nearest pyproject.toml at or above `path`.

        Raises:
            SettingsError: the file is not TOML, or the table is malformed.
        """
        root = project_root(path)
        return cls.parse(root / "pyproject.toml") if root else cls(enabled=False)

    @classmethod
    def parse(cls, pyproject: Path) -> Settings:
        """Return the settings that `pyproject` declares."""
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            raise SettingsError(f"{pyproject}: cannot read it as TOML ({e})") from e
        table = data.get("tool", {}).get("conventions")
        if table is None:
            return cls(enabled=False)
        if not isinstance(table, dict):
            raise SettingsError(f"{pyproject}: `tool.conventions` must be a table")
        if unknown := sorted(set(table) - KEYS):
            raise SettingsError(
                f"{pyproject}: unknown key {', '.join(unknown)} in [tool.conventions]; "
                f"known: {', '.join(sorted(KEYS))}"
            )
        ignore = table.get("ignore", [])
        if not isinstance(ignore, list) or not all(
            isinstance(rule, str) and RULE_ID.fullmatch(rule) for rule in ignore
        ):
            raise SettingsError(
                f"{pyproject}: [tool.conventions] ignore must list rule IDs; "
                'write it as ignore = ["STY-4"]'
            )
        review = table.get("review", True)
        if not isinstance(review, bool):
            raise SettingsError(
                f"{pyproject}: [tool.conventions] review must be true or false; "
                "write it as review = false"
            )
        return cls(enabled=True, ignore=frozenset(ignore), review=review)

    def keeps(self, rule: str) -> bool:
        """Return whether this repo checks `rule`."""
        return rule not in self.ignore


def project_root(path: Path) -> Path | None:
    """Return the nearest directory at or above `path` with a pyproject.toml, if any."""
    start = path.absolute()
    for directory in (start, *start.parents):
        if (directory / "pyproject.toml").is_file():
            return directory
    return None

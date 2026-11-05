"""The `[tool.conventions]` table that opts a repo in and turns rules off."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from attrs import frozen

RULE_ID = re.compile(r"[A-Z]+-\d+")
KEYS = frozenset({"ignore"})


class SettingsError(Exception):
    """A `[tool.conventions]` table that does not parse as documented."""


@frozen
class Settings:
    """What a repo's `[tool.conventions]` table says; `enabled` when it has one."""

    enabled: bool
    ignore: frozenset[str] = frozenset()

    @classmethod
    def of(cls, path: Path) -> Settings:
        """Return the settings of the nearest pyproject.toml at or above `path`.

        Raises:
            SettingsError: the file is not TOML, or the table is malformed.
        """
        start = path.absolute()
        for directory in (start, *start.parents):
            pyproject = directory / "pyproject.toml"
            if pyproject.is_file():
                return cls.parse(pyproject)
        return cls(enabled=False)

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
        return cls(enabled=True, ignore=frozenset(ignore))

    def keeps(self, rule: str) -> bool:
        """Return whether this repo checks `rule`."""
        return rule not in self.ignore

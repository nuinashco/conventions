"""Comments that waive a rule at one line, as `# conventions: TYP-4 - why.` does."""

from __future__ import annotations

import re

WAIVER = re.compile(r"#\s*conventions:\s*([A-Z]+-\d+)")


def waived(source: str) -> dict[int, set[str]]:
    """Return the rules waived at each line of `source`.

    A waiver covers its own line, and the line below when it stands alone on its own.
    """
    lines: dict[int, set[str]] = {}
    for number, line in enumerate(source.splitlines(), start=1):
        rules = set(WAIVER.findall(line))
        lines.setdefault(number, set()).update(rules)
        if rules and line.lstrip().startswith("#"):
            lines.setdefault(number + 1, set()).update(rules)
    return lines

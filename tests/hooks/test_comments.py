"""The comment checker flags non-sentences, banners and imperative class docstrings."""

from __future__ import annotations

import json

import pytest

from conventions_hooks.comments import check_source, claude_hook, main


def rules(source: str) -> list[tuple[int, str]]:
    return [(f.line, f.rule) for f in check_source(source)]


@pytest.mark.parametrize(
    "source",
    [
        "x = 1  # Seconds, measured on Kaggle.\n",
        "# `swegemma` runs every task when the list is empty.\nx = 1\n",
        "# cuBLAS refuses deterministic GEMMs without a workspace.\nx = 1\n",
        "# A block whose sentence\n# ends on its second line.\nx = 1\n",
        "# See the scorer's notes:\n# https://example.com/notes\nx = 1\n",
        "x = f()  # noqa: BLE001\n",
        "x = 1  # type: ignore[assignment]\n",
        "#!/usr/bin/env python\n",
        'class Proxy:\n    """Endpoint wrapper adding limits and the call log."""\n',
    ],
    ids=[
        "inline",
        "backticked-name",
        "mixed-case-name",
        "multi-line",
        "url-last",
        "noqa",
        "directive",
        "shebang",
        "noun-phrase",
    ],
)
def test_conforming_comments_pass(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x = 1  # seconds.\n", [(1, "DOC-5")]),
        ("# Seconds per request\nx = 1\n", [(1, "DOC-5")]),
        ("# First line.\n#\n# last line without end\nx = 1\n", [(3, "DOC-5")]),
        ("# ---- Override points ----\nx = 1\n", [(1, "DOC-4")]),
        ("## Section.\nx = 1\n", [(1, "DOC-4")]),
        ('class A:\n    """Return the rate limit."""\n', [(1, "DOC-2")]),
    ],
    ids=["lowercase", "no-period", "block-end", "banner", "heading", "class-order"],
)
def test_broken_rules_are_reported_where_they_happen(source, expected):
    assert rules(source) == expected


def test_the_claude_hook_reports_an_edited_python_file(tmp_path, capsys):
    module = tmp_path / "module.py"
    module.write_text("x = 1  # seconds.\n")
    notes = tmp_path / "notes.md"
    notes.write_text("# notes\n")

    def payload(path: object) -> str:
        return json.dumps({"tool_input": {"file_path": str(path)}})

    assert claude_hook(payload(notes)) == 0
    assert claude_hook(payload(module)) == 2
    assert "DOC-5" in capsys.readouterr().err


def test_flags_print_the_usage_instead_of_reading_files(capsys):
    assert (main(["--help"]), main(["--bogus"])) == (0, 2)
    assert "Usage:" in capsys.readouterr().out

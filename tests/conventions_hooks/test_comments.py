"""The comment checker flags non-sentences, banners and imperative class docstrings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conventions_hooks.comments import check_file, check_source, claude_hook, main

PEP_723 = (
    "# /// script\n"
    '# requires-python = ">=3.12"\n'
    '# dependencies = ["polars>=1.0"]\n'
    "# ///\n"
)


def rules(source: str) -> list[tuple[int, str]]:
    return [(f.line, f.rule) for f in check_source(source)]


def rules_of(path: Path) -> list[tuple[int, str]]:
    return [(f.line, f.rule) for f in check_file(path)]


def edit(path: Path) -> str:
    return json.dumps({"tool_input": {"file_path": str(path)}})


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
        ("# Override points ====\nx = 1\n", [(1, "DOC-4")]),
        ("# Loading.\n##\n# Saving.\nx = 1\n", [(2, "DOC-4")]),
        ("x = 1  # ---- seconds ----\n", [(1, "DOC-5")]),
        ('class A:\n    """Return the rate limit."""\n', [(1, "DOC-2")]),
        ('class A:\n    """Run `make check`."""\n', [(1, "DOC-2")]),
        ('class A:\n    """Serve."""\n', [(1, "DOC-2")]),
    ],
    ids=[
        "lowercase",
        "no-period",
        "block-end",
        "banner",
        "heading",
        "rule-at-the-end",
        "empty-heading",
        "rule-after-code",
        "class-order",
        "class-order-on-a-name",
        "class-order-alone",
    ],
)
def test_broken_rules_are_reported_where_they_happen(source, expected):
    assert rules(source) == expected


def test_an_order_is_named_without_its_punctuation():
    (finding,) = check_source('class A:\n    """Serve."""\n')

    assert "('Serve')" in finding.message


@pytest.mark.parametrize(
    "docstring",
    [
        "Run directory of one experiment.",
        "Stop condition for early stopping.",
        "Update rule of the optimiser.",
        "Handle to a served model.",
        "Call arguments recorded by the fake endpoint.",
        "Run: the loop that drives one experiment.",
        "\n    ",
        "Run settings: its name and its seed.",
        "Call of one tool by the model.",
        "Return code of a finished child process.",
    ],
    ids=[
        "run",
        "stop",
        "update",
        "handle",
        "call",
        "label",
        "only-whitespace",
        "run-settings",
        "call-of",
        "return-code",
    ],
)
def test_a_class_docstring_that_may_open_with_a_noun_passes(docstring):
    assert rules(f'class A:\n    """{docstring}"""\n\n    steps = None\n') == []


@pytest.mark.parametrize(
    "docstring",
    [
        "Convert tabs to spaces.",
        "Manage resource extraction.",
        "Return the rate limit.",
        "Build `x` from the settings.",
        "Load one checkpoint.",
        "Run.",
    ],
    ids=[
        "convert",
        "manage",
        "noun-too-before-a-determiner",
        "noun-too-before-a-name",
        "noun-too-before-a-number",
        "noun-too-alone",
    ],
)
def test_a_class_docstring_that_opens_with_an_order_is_reported(docstring):
    assert rules(f'class A:\n    """{docstring}"""\n') == [(1, "DOC-2")]


@pytest.mark.parametrize(
    "source",
    [
        "RATE = 0.5  # We clip the rate --- see section 3 of the paper.\n",
        'COLOR = "#fff"  # #rgb hex format, shorthand for #rrggbb.\n',
        'SUMMARY = "ok"  # `pytest` prints "=== 3 passed ===" on the last line.\n',
        "# YAML documents are separated by --- lines, so split on that.\nPARTS = 1\n",
        "# JavaScript's === has no Python equivalent; compare with == here.\nX = 2\n",
        "# Keys are logged as sk-**** only.\nKEY = 3\n",
        "# #rrggbb hex format.\nCOLOR = 4\n",
    ],
    ids=[
        "dashes-after-code",
        "hex-colour-after-code",
        "equals-after-code",
        "dashes",
        "equals",
        "stars",
        "hex-colour",
    ],
)
def test_a_sentence_that_holds_rule_characters_is_no_banner(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    "comment",
    [
        "# %%",
        "# %% [markdown]",
        "# In[3]",
        "#: Seconds before a request times out",
        "# nosec B404",
        "# pylint: disable=invalid-name",
        "# flake8: noqa",
        "# ty: ignore[unresolved-import]",
        "# pyre-ignore[16]",
        "# pytype: disable=attribute-error",
        "# pyrefly: ignore",
        "# basedpyright: ignore[reportAny]",
        "# yapf: disable",
        "# codespell:ignore teh",
        "# cspell:ignore conftest",
        "# region imports",
        "# endregion",
        "# SPDX-License-Identifier: MIT",
        "# NOQA",
        "#NoQA: E501",
        "# seconds  # NOQA: E501",
    ],
    ids=[
        "cell",
        "markdown-cell",
        "nbconvert-cell",
        "attribute",
        "nosec",
        "pylint",
        "flake8",
        "ty",
        "pyre",
        "pytype",
        "pyrefly",
        "basedpyright",
        "yapf",
        "codespell",
        "cspell",
        "region",
        "endregion",
        "spdx",
        "noqa-in-capitals",
        "noqa-in-mixed-case",
        "noqa-after-text",
    ],
)
def test_a_comment_that_a_tool_reads_is_no_sentence(comment):
    assert rules(f"{comment}\nx = 1\n") == []
    assert rules(f"x = 1  {comment}\n") == []


def test_a_pep_723_block_is_skipped_and_the_comments_around_it_are_not():
    source = (
        f'#!/usr/bin/env -S uv run\n{PEP_723}"""Print it."""\n\nx = 1  # seconds.\n'
    )

    assert rules(source) == [(8, "DOC-5")]


def test_an_opening_line_of_pep_723_without_a_closing_one_skips_nothing():
    assert rules(PEP_723.removesuffix("# ///\n") + "x = 1\n") == [(3, "DOC-5")]


@pytest.mark.parametrize(
    "between",
    ["x = 1\n", "\n", "x = 1  # A pin.\n", "    # A pin.\n"],
    ids=["code", "blank-line", "comment-after-code", "indented-comment"],
)
def test_a_line_that_is_no_comment_at_the_margin_ends_a_pep_723_block(between):
    source = f'# /// script\n# requires-python = ">=3.12"\n{between}# seconds\n# ///\n'

    assert rules(source) == [(2, "DOC-5"), (4, "DOC-5"), (5, "DOC-5")]


@pytest.mark.parametrize(
    "source",
    [
        'class A:  # conventions: DOC-2 - a command object.\n    """Run the job."""\n',
        '# conventions: DOC-2 - a command object.\nclass A:\n    """Run the job."""\n',
        "# conventions: DOC-4 - the spec's own heading.\n## Section.\nx = 1\n",
        "# conventions: DOC-5 - a unit.\nx = 1  # seconds\n",
        "x = 1  # seconds  # conventions: DOC-5 - a unit.\n",
    ],
    ids=["class-line", "above-class", "above-banner", "above-comment", "same-line"],
)
def test_a_waiver_comment_drops_the_finding_at_its_line(source):
    assert rules(source) == []


def test_a_waiver_that_names_another_rule_drops_nothing():
    source = "x = 1  # seconds  # conventions: DOC-4 - wrong rule.\n"

    assert rules(source) == [(1, "DOC-5")]


def test_a_waiver_above_the_decorators_of_a_class_covers_its_docstring():
    decorated = '@frozen\nclass A:\n    """Run the thing."""\n\n    name: str\n'
    waiver = "# conventions: DOC-2 - a command object.\n"

    assert (rules(decorated), rules(waiver + decorated)) == ([(2, "DOC-2")], [])


@pytest.mark.parametrize(
    ("waiver", "below", "alone"),
    [
        (
            "# conventions: STY-4 - OmegaConf passes arguments by position, and\n",
            "# a second line finishes the reason.\ndef env_or(name, default=''): ...\n",
            [(1, "DOC-5")],
        ),
        (
            "# conventions: DOC-5 - a table aligned by hand.\n",
            "# name     seconds\n# fast     0.1\nX = 1\n",
            [(1, "DOC-5"), (2, "DOC-5")],
        ),
    ],
    ids=["reason-on-two-lines", "table-aligned-by-hand"],
)
def test_comment_lines_right_below_a_waiver_are_not_judged(waiver, below, alone):
    assert (rules(below), rules(waiver + below)) == (alone, [])


def test_a_comment_that_only_quotes_a_waiver_is_judged_with_the_lines_below_it():
    source = (
        "# A waiver reads `# conventions: TYP-4 - why` and stands above the\n"
        "# class that it is for\n"
        "X = 1\n"
    )

    assert rules(source) == [(2, "DOC-5")]


def test_a_waiver_above_a_statement_covers_neither_its_body_nor_what_follows():
    source = (
        "# conventions: DOC-5 - a unit.\n"
        "def wait():  # seconds\n"
        "    return 1  # seconds.\n"
        "# seconds.\n"
        "LIMIT = 2\n"
    )

    assert rules(source) == [(3, "DOC-5"), (4, "DOC-5")]


def test_line_numbers_follow_the_tokenizer_past_a_form_feed():
    source = (
        "import os\n\x0c\n\n"
        "def load():  # seconds.\n"
        "    # A comment that spans\n    # two lines.\n"
        "    return os\n"
    )

    assert rules(source) == [(4, "DOC-5")]


@pytest.mark.parametrize(
    "source",
    [
        "VALUES = [\n    1,  # seconds\n",
        'NAME = "abc\n',
        "def f():\n        x = 1\n    y = 2\n",
        "def f():\n\tif True:\n        x = 1\n\ty = 2\n",
        "x = 1\x00  # seconds\n",
        "x = = 1  # seconds\n",
        "x = a" + ".b" * 100_000 + "\n",
        "x = " + "-" * 20_000 + "1\n",
    ],
    ids=[
        "unclosed-bracket",
        "unterminated-string",
        "bad-dedent",
        "tabs-and-spaces",
        "null-byte",
        "syntax-error",
        "too-deep-to-compile",
        "too-deep-to-parse",
    ],
)
def test_a_source_that_python_cannot_parse_has_no_findings(source):
    assert rules(source) == []


def test_a_file_is_read_the_way_python_reads_it(tmp_path):
    bom = tmp_path / "bom.py"
    bom.write_bytes(b'\xef\xbb\xbfclass A:\n    """Return the rate limit."""\n')
    latin = tmp_path / "latin.py"
    latin.write_bytes(b"# -*- coding: latin-1 -*-\nNAME = 'caf\xe9'  # seconds.\n")

    assert (rules_of(bom), rules_of(latin)) == ([(1, "DOC-2")], [(2, "DOC-5")])


@pytest.mark.parametrize(
    "data",
    [
        b"# caf\xe9\nx = 1  # seconds\n",
        b"x = 1  # seconds\ny = 2\nz = '\xff\xfe'\n",
        b"# coding: uft-8\nx = 1  # seconds\n",
        b"# coding: hex\nx = 1  # seconds\n",
    ],
    ids=[
        "latin-1-undeclared",
        "bytes-that-are-not-utf-8",
        "unknown-encoding",
        "codec-that-is-no-text-encoding",
    ],
)
def test_a_file_that_python_cannot_read_has_no_findings(tmp_path, data):
    module = tmp_path / "module.py"
    module.write_bytes(data)

    assert check_file(module) == []


def test_the_command_line_and_the_hook_pass_a_file_python_cannot_read(opted_in, capsys):
    half = opted_in / "half.py"
    half.write_text("VALUES = [\n    1,  # seconds\n")
    latin = opted_in / "latin.py"
    latin.write_bytes(b"# caf\xe9\nX = 1\n")

    assert main([str(half), str(latin)]) == 0
    assert (claude_hook(edit(half)), claude_hook(edit(latin))) == (0, 0)
    assert capsys.readouterr() == ("", "")


def test_the_claude_hook_reports_an_edited_python_file(opted_in, capsys):
    module = opted_in / "module.py"
    module.write_text("x = 1  # seconds.\n")
    notes = opted_in / "notes.md"
    notes.write_text("# notes\n")

    def payload(path: object) -> str:
        return json.dumps({"tool_input": {"file_path": str(path)}})

    assert claude_hook(payload(notes)) == 0
    assert claude_hook(payload(module)) == 2
    assert "DOC-5" in capsys.readouterr().err


def test_flags_print_the_usage_instead_of_reading_files(capsys):
    assert (main(["--help"]), main(["--bogus"])) == (0, 2)
    assert "Usage:" in capsys.readouterr().out

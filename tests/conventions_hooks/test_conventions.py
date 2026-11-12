"""The convention checker flags the code rules an AST can decide, and only those."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conventions_hooks.conventions import check_file, check_source, claude_hook, main

PACKAGE = "src/demo/endpoints/runner.py"


def rules(source: str, path: str = PACKAGE) -> list[tuple[int, str]]:
    return [(f.line, f.rule) for f in check_source(source, path=path)]


def rules_of(path: Path) -> list[tuple[int, str]]:
    return [(f.line, f.rule) for f in check_file(path)]


def edit(path: Path) -> str:
    return json.dumps({"tool_input": {"file_path": str(path)}})


@pytest.mark.parametrize(
    "source",
    [
        "@EndpointFactory.register('litellm')\n@define\nclass LiteLLM:\n    x: int\n",
        "class ProxyError(UserError):\n    def __init__(self) -> None: ...\n",
        "class Clock(Protocol):\n    def __init__(self) -> None: ...\n",
        "def build(config, *, retries=3): ...\n",
        "def main(argv=None): ...\n",
        "if item.requires_hardware:\n    pass\n",
        "log.info('proxy_started', port=8000)\n",
        "raise UserError(f'no soundness data; run `{cmd}` first')\n",
        "raise ConfigError('PROJECT_ROOT is unset; run from the repo')\n",
        "raise ValueError(' ')\n",
        "raise ValueError('\\n')\n",
        "raise ValueError(f' ')\n",
        "DASH = '\\u2014'\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import torch\n",
        "def load():\n    import torch\n",
        "ROOT = rootutils.find_root(search_from=__file__)\n",
        "x = os.environ  # conventions: ENV-3 - the hook has no paths.py.\n",
        "# conventions: ENV-3 - the hook has no paths.py.\nx = os.environ\n",
    ],
    ids=[
        "register-outermost",
        "exception-init",
        "protocol-init",
        "keyword-only-option",
        "console-main",
        "capability-flag",
        "snake-case-event",
        "lowercase-message",
        "message-opens-with-a-name",
        "blank-message",
        "newline-message",
        "blank-f-string-message",
        "escape-for-a-dash",
        "type-checking-import",
        "lazy-import",
        "rootutils",
        "allowed-inline",
        "allowed-above",
    ],
)
def test_conforming_code_passes(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("@define\n@ShapeFactory.register('x')\nclass A: ...\n", [(2, "FAM-2")]),
        ("class A:\n    def __init__(self):\n        pass\n", [(2, "TYP-4")]),
        ("@dataclass\nclass A:\n    x: int\n", [(1, "TYP-4")]),
        ("from dataclasses import dataclass\n", [(1, "TYP-4")]),
        ("def build(config, retries=3): ...\n", [(1, "STY-4")]),
        ("if item.kind == 'api':\n    pass\n", [(1, "ARC-4")]),
        ("log.info(f'started on {port}')\n", [(1, "LOG-2")]),
        ("log.info('Proxy started')\n", [(1, "LOG-2")]),
        ("raise UserError('Missing data.')\n", [(1, "ERR-3"), (1, "ERR-3")]),
        ("import torch\n", [(1, "ARC-8")]),
        ("from google.cloud import bigquery\n", [(1, "ARC-8")]),
        ("ROOT = Path(__file__).resolve().parents[2]\n", [(1, "ENV-1")]),
        ("ROOT = Path(__file__).parent.parent\n", [(1, "ENV-1")]),
        ("token = os.environ['TOKEN']\n", [(1, "ENV-3")]),
        ("x = os.environ  # conventions: TYP-4 - wrong rule.\n", [(1, "ENV-3")]),
    ],
    ids=[
        "register-inside",
        "init",
        "dataclass",
        "dataclasses-import",
        "positional-option",
        "kind-equals",
        "f-string-event",
        "sentence-event",
        "capitalised-message-with-period",
        "eager-torch",
        "eager-cloud-sdk",
        "file-parents",
        "file-parent-parent",
        "environ",
        "allow-names-another-rule",
    ],
)
def test_broken_rules_are_reported_where_they_happen(source, expected):
    assert rules(source) == expected


def test_findings_on_one_line_keep_the_order_they_were_met_in():
    source = "def handle(item, h=1, g=2, f=3, e=4, d=5, c=6, b=7, a=8): ...\n"

    named = [f.message.split("`")[1] for f in check_source(source, path=PACKAGE)]

    assert named == list("hgfedcba")


def test_a_character_outside_ascii_is_reported_once_per_line_by_its_code_point():
    source = 'DASH = "\u2014 or \u2192"\nPLAIN = 1\nMICRO = "\u00b5s"  # Unit.\n'

    findings = check_source(source, path=PACKAGE)

    assert [(f.line, f.rule) for f in findings] == [(1, "STY-8"), (3, "STY-8")]
    assert findings[0].message == (
        "non-ASCII character U+2014; write it in ASCII or as an escape"
    )


def test_tests_are_ascii_too_and_a_waiver_allows_one_line():
    source = (
        'ARROW = "\u2192"\n'
        'DASH = "\u2014"  # conventions: STY-8 - the page prints this dash.\n'
    )

    assert rules(source, "tests/demo/test_page.py") == [(1, "STY-8")]


@pytest.mark.parametrize(
    "source",
    [
        "def load(path, strict=False):\n    return [\n",
        "x = = '\u2014'\n",
        "def load(path, strict=False): ...\nx = 1\x00\n",
        "x = a" + ".b" * 100_000 + "\n",
        "x = " + "-" * 20_000 + "1\n",
    ],
    ids=[
        "unclosed-bracket",
        "syntax-error-with-a-dash",
        "null-byte",
        "too-deep-to-compile",
        "too-deep-to-parse",
    ],
)
def test_a_source_that_python_cannot_parse_has_no_findings(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "def total(a, start=0):\n    return " + " + ".join(["a"] * 3000) + "\n",
            [(1, "STY-4")],
        ),
        (
            "def build(q, start=0):\n    return q" + ".where(1)" * 1000 + "\n",
            [(1, "STY-4")],
        ),
        (
            "def pick(x):\n    if x == 'v0':\n        return 0\n"
            + "".join(
                f"    elif x == 'v{i}':\n        return {i}\n" for i in range(1, 1100)
            ),
            [(2, "ARC-9")],
        ),
        (
            "class A(B" + "[0]" * 1500 + "):\n    def __init__(self): ...\n",
            [(2, "TYP-4")],
        ),
        (
            "class A(Protocol" + "[0]" * 1500 + "):\n    def __init__(self): ...\n",
            [],
        ),
    ],
    ids=[
        "long-sum",
        "long-call-chain",
        "long-elif-chain",
        "long-subscript",
        "long-subscript-of-a-protocol",
    ],
)
def test_code_nested_deeper_than_the_recursion_limit_is_checked(source, expected):
    assert rules(source) == expected


def test_a_waiver_is_found_on_its_line_past_a_form_feed():
    source = (
        "import os\n\x0c\n\n"
        "def load(path, strict=False):  # conventions: STY-4 - passed by position.\n"
        "    return os.fspath(path), strict\n"
    )

    assert rules(source) == []


def test_a_file_is_read_the_way_python_reads_it(tmp_path):
    bom = tmp_path / "bom.py"
    bom.write_bytes(b"\xef\xbb\xbfdef load(path, strict=False): ...\n")
    latin = tmp_path / "latin.py"
    latin.write_bytes(
        b"# -*- coding: latin-1 -*-\ndef load(path, strict=False):\n"
        b"    return 'caf\xe9'\n"
    )

    assert rules_of(bom) == [(1, "STY-4")]
    assert rules_of(latin) == [(2, "STY-4"), (3, "STY-8")]


@pytest.mark.parametrize(
    "data",
    [
        b"# caf\xe9\ndef load(path, strict=False): ...\n",
        b"def load(path, strict=False): ...\n\nNAME = '\xff\xfe'\n",
        b"# coding: uft-8\ndef load(path, strict=False): ...\n",
        b"# coding: hex\ndef load(path, strict=False): ...\n",
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
    latin = opted_in / "latin.py"
    latin.write_bytes(b"# caf\xe9\ndef load(path, strict=False): ...\n")

    assert (main([str(latin)]), claude_hook(edit(latin))) == (0, 0)
    assert capsys.readouterr() == ("", "")


def test_paths_module_may_read_the_environment():
    source = "DATA_DIR = Path(os.environ['DATA_DIR'])\n"

    assert rules(source, "src/demo/paths.py") == []


def test_paths_rules_apply_only_in_a_project_with_a_paths_module(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    module = tmp_path / "src" / "demo" / "runner.py"
    module.parent.mkdir(parents=True)
    module.write_text("ROOT = Path(__file__).parents[2]\nTOKEN = os.environ['T']\n")

    before = [f.rule for f in check_file(module)]
    (module.parent / "paths.py").write_text("ROOT = 1\n")
    after = [f.rule for f in check_file(module)]

    assert (before, after) == ([], ["ENV-1", "ENV-3"])


def test_tests_may_use_kinds_environ_and_positional_defaults():
    source = (
        "def helper(x, y=1): ...\n"
        "assert item.kind == 'api'\n"
        "assert os.environ['PROJECT_ROOT']\n"
    )

    assert rules(source, "tests/demo/test_runner.py") == []


def test_test_classes_are_reported_only_in_tests():
    source = "class TestRunner:\n    x = 1\n"

    assert rules(source, "tests/test_runner.py") == [(1, "TST-1")]
    assert rules(source) == []


def test_grab_bag_modules_are_reported_inside_the_package():
    assert rules("x = 1\n", "src/demo/utils.py") == [(1, "LAY-2")]
    assert rules("x = 1\n", "src/demo/common/text.py") == [(1, "LAY-2")]
    assert rules("x = 1\n", "scripts/utils.py") == []


def test_eager_heavy_imports_are_allowed_outside_the_package():
    assert rules("import torch\n", "scripts/train_once.py") == []


def test_folders_above_the_project_do_not_change_which_rules_apply(tmp_path):
    project = tmp_path / "tests" / "src" / "core"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "scripts").mkdir()
    (project / "pyproject.toml").write_text("[tool.conventions]\n")
    module = project / "src" / "demo" / "mod.py"
    module.write_text("import torch\n\n\nclass TestThing:\n    x = 1\n")
    script = project / "scripts" / "once.py"
    script.write_text("import torch\n")

    found = [[(f.line, f.rule) for f in check_file(path)] for path in (module, script)]

    assert found == [[(1, "ARC-8")], []]


def test_the_claude_hook_reports_an_edited_python_file(opted_in, capsys):
    module = opted_in / "src" / "demo" / "runner.py"
    module.parent.mkdir(parents=True)
    module.write_text("if item.kind == 'api':\n    pass\n")
    notes = opted_in / "notes.md"
    notes.write_text("kind == api\n")

    def payload(path: object) -> str:
        return json.dumps({"tool_input": {"file_path": str(path)}})

    assert claude_hook(payload(notes)) == 0
    assert claude_hook(payload(module)) == 2
    assert "ARC-4" in capsys.readouterr().err


def test_flags_print_the_usage_instead_of_reading_files(capsys):
    assert (main(["--help"]), main(["--bogus"])) == (0, 2)
    assert "Usage:" in capsys.readouterr().out


def test_tests_may_switch_on_variants():
    source = (
        "def score(metric):\n"
        "    if metric == 'f1':\n        return f1()\n"
        "    elif metric == 'em':\n        return exact()\n"
        "    elif metric == 'bleu':\n        return bleu()\n"
    )

    assert rules(source) == [(2, "ARC-9")]
    assert rules(source, "tests/demo/test_metrics.py") == []

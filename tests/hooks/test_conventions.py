"""The convention checker flags the code rules an AST can decide, and only those."""

from __future__ import annotations

import json

import pytest

from conventions_hooks.conventions import check_source, claude_hook, main

PACKAGE = "src/demo/endpoints/runner.py"


def rules(source: str, path: str = PACKAGE) -> list[tuple[int, str]]:
    return [(f.line, f.rule) for f in check_source(source, path=path)]


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


def test_paths_module_may_read_the_environment():
    source = "DATA_DIR = Path(os.environ['DATA_DIR'])\n"

    assert rules(source, "src/demo/paths.py") == []


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


def test_the_claude_hook_reports_an_edited_python_file(tmp_path, capsys):
    module = tmp_path / "src" / "demo" / "runner.py"
    module.parent.mkdir(parents=True)
    module.write_text("if item.kind == 'api':\n    pass\n")
    notes = tmp_path / "notes.md"
    notes.write_text("kind == api\n")

    def payload(path: object) -> str:
        return json.dumps({"tool_input": {"file_path": str(path)}})

    assert claude_hook(payload(notes)) == 0
    assert claude_hook(payload(module)) == 2
    assert "ARC-4" in capsys.readouterr().err


def test_flags_print_the_usage_instead_of_reading_files(capsys):
    assert (main(["--help"]), main(["--bogus"])) == (0, 2)
    assert "Usage:" in capsys.readouterr().out

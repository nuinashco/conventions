"""The convention checker flags the code rules an AST can decide, and only those."""

from __future__ import annotations

import json
import re
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
        "x = os.environ['T']  # conventions: ENV-3 - the hook has no paths.py.\n",
        "# conventions: ENV-3 - the hook has no paths.py.\nx = os.environ['T']\n",
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
        ("@dataclass(frozen=True)\nclass A:\n    x: int\n", [(1, "TYP-4")]),
        ("from dataclasses import dataclass\n", [(1, "TYP-4")]),
        ("def build(config, retries=3): ...\n", [(1, "STY-4")]),
        ("if item.kind == 'api':\n    pass\n", [(1, "ARC-4")]),
        ("log.info(f'started on {port}')\n", [(1, "LOG-2")]),
        ("log.info('Proxy started')\n", [(1, "LOG-2")]),
        ("raise UserError('Missing data.')\n", [(1, "ERR-3")]),
        ("import torch\n", [(1, "ARC-8")]),
        ("from google.cloud import bigquery\n", [(1, "ARC-8")]),
        ("ROOT = Path(__file__).resolve().parents[2]\n", [(1, "ENV-1")]),
        ("ROOT = Path(__file__).parent.parent\n", [(1, "ENV-1")]),
        ("token = os.environ['TOKEN']\n", [(1, "ENV-3")]),
        ("x = os.environ['T']  # conventions: TYP-4 - wrong rule.\n", [(1, "ENV-3")]),
    ],
    ids=[
        "register-inside",
        "init",
        "dataclass",
        "dataclass-called",
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


def test_an_optional_parameter_is_told_to_go_after_the_star_or_be_waived():
    (finding,) = check_source("def env_or(name, default=''): ...\n", path=PACKAGE)

    assert finding.message == (
        "optional parameter `default` goes after `*`, keyword-only, unless a caller "
        "outside the project fixes the signature: then waive it"
    )


def test_optional_parameters_on_one_line_are_one_finding_in_their_order():
    source = (
        "def handle(\n    item, h=1, g=2, f=3, e=4, d=5, c=6, b=7,\n    a=8,\n): ...\n"
    )

    found = check_source(source, path=PACKAGE)

    assert [(f.line, f.message) for f in found] == [
        (
            2,
            "optional parameters `h`, `g`, `f`, `e`, `d`, `c`, `b` go after `*`, "
            "keyword-only, unless a caller outside the project fixes the signature: "
            "then waive it",
        ),
        (
            3,
            "optional parameter `a` goes after `*`, keyword-only, unless a caller "
            "outside the project fixes the signature: then waive it",
        ),
    ]


def test_two_findings_of_one_rule_on_one_line_are_one_with_both_remedies(
    tmp_path, capsys
):
    module = tmp_path / "loader.py"
    module.write_text("def load():\n    raise UserError('Missing data.')\n")

    assert main([str(module)]) == 1
    assert capsys.readouterr().out == (
        f"{module}:2: ERR-3 error messages start lowercase; "
        "error messages have no trailing period\n"
    )


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
    source = "class TestRunner:\n    def test_it_runs(self): ...\n"

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
    module.write_text(
        "import torch\n\n\nclass TestThing:\n    def test_it(self): ...\n"
    )
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


def test_a_waived_switch_does_not_count_against_the_rest_of_its_module():
    source = (
        "def start(backend):\n"
        "    # conventions: ARC-9 - the launchers differ too much to share a class.\n"
        "    if backend == 'modal':\n        launch_modal()\n"
        "    elif backend == 'local':\n        launch_local()\n\n\n"
        "def cost_usd(backend):\n"
        "    if backend == 'modal':\n        return 0.3\n"
        "    return 0.0\n"
    )

    assert rules(source) == []
    assert rules(source.replace("conventions: ARC-9", "note")) == [(10, "ARC-9")]
    assert rules(source.replace("ARC-9", "STY-4")) == [(10, "ARC-9")]


def test_a_waiver_above_a_guard_with_no_arm_waives_its_run_of_guards():
    source = (
        "def render(rows, *, fmt):\n"
        "    # conventions: ARC-9 - the formats share nothing worth a class.\n"
        "    if fmt == '':\n        return to_text(rows)\n"
        "    if fmt == 'csv':\n        return to_csv(rows)\n"
        "    if fmt == 'json':\n        return to_json(rows)\n"
        "    if fmt == 'md':\n        return to_markdown(rows)\n"
        "    raise UnknownFormatError(fmt)\n\n\n"
        "def header(fmt):\n    if fmt == 'csv':\n        return 'a,b'\n"
    )

    assert rules(source) == []
    assert rules(source.replace("conventions: ARC-9", "note")) == [
        (5, "ARC-9"),
        (15, "ARC-9"),
    ]


def rules_in_demo(source: str) -> list[tuple[int, str]]:
    """Return the findings for a module of a project whose own package is `demo`."""
    found = check_source(source, path=PACKAGE, own_packages={"demo"})
    return [(f.line, f.rule) for f in found]


INIT = "    def __init__(self): ...\n"


@pytest.mark.parametrize(
    "source",
    [
        f"from torch import nn\n\n\nclass Perceptron(nn.Module):\n{INIT}",
        f"import logging\n\n\nclass ListHandler(logging.Handler):\n{INIT}",
        f"from threading import Thread\n\n\nclass Worker(Thread):\n{INIT}",
        f"import argparse as cli\n\n\nclass Append(cli.Action):\n{INIT}",
        f"import enum\n\n\nclass Permission(enum.Flag):\n{INIT}",
        f"from lib.rows import Rows\n\n\nclass Ints(Rows[int]):\n{INIT}",
        f"import lib.rows\n\n\nclass Ints(lib.rows.Rows[int]):\n{INIT}",
        f"from abc import ABC\nfrom lib import Row\n\n\nclass Step(Row, ABC):\n{INIT}",
        (
            "from torch import nn\n\n\nclass Block(nn.Module): ...\n\n\n"
            f"class Decoder(Block):\n{INIT}"
        ),
        (
            f"from torch import nn\n\n\nclass Decoder(Block):\n{INIT}\n\n"
            "class Block(nn.Module): ...\n"
        ),
        (
            "def build():\n    from torch import nn\n\n"
            "    class Head(nn.Module):\n        def __init__(self): ...\n\n"
            "    return Head()\n"
        ),
    ],
    ids=[
        "torch-module",
        "logging-handler",
        "imported-class",
        "module-under-another-name",
        "enum-flag",
        "subscripted-base",
        "dotted-module",
        "outside-base-beside-abc",
        "base-in-this-module-from-outside",
        "base-in-this-module-defined-below",
        "import-inside-a-function",
    ],
)
def test_a_subclass_of_a_class_from_outside_the_project_keeps_its_init(source):
    assert rules_in_demo(source) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (f"from abc import ABC\n\n\nclass Endpoint(ABC):\n{INIT}", [(5, "TYP-4")]),
        (f"import abc\n\n\nclass Endpoint(abc.ABC):\n{INIT}", [(5, "TYP-4")]),
        (
            f"from typing import Generic\n\n\nclass Box(Generic[T]):\n{INIT}",
            [(5, "TYP-4")],
        ),
        (f"class Plain(object):\n{INIT}", [(2, "TYP-4")]),
        (
            f"from demo.endpoints.base import Endpoint\n\n\nclass A(Endpoint):\n{INIT}",
            [(5, "TYP-4")],
        ),
        (
            f"import demo.base\n\n\nclass Api(demo.base.Endpoint):\n{INIT}",
            [(5, "TYP-4")],
        ),
        (
            f"from .base import Endpoint\n\n\nclass Api(Endpoint):\n{INIT}",
            [(5, "TYP-4")],
        ),
        (f"class Base: ...\n\n\nclass Item(Base):\n{INIT}", [(5, "TYP-4")]),
        (f"Base = make_base()\n\n\nclass Item(Base):\n{INIT}", [(5, "TYP-4")]),
        (f"class A(B):\n{INIT}\n\nclass B(A): ...\n", [(2, "TYP-4")]),
        ("@dataclass\nclass A(ABC):\n    x: int\n", [(1, "TYP-4")]),
        (
            "from torch import nn\n\n\n@dataclass\nclass A(nn.Module):\n    x: int\n",
            [(4, "TYP-4")],
        ),
        (
            "from abc import ABC\n\nfrom nuikit.registry import Configurable\n\n\n"
            f"class Signal(Configurable[C], ABC):\n{INIT}",
            [(7, "TYP-4")],
        ),
    ],
    ids=[
        "abc",
        "dotted-abc",
        "generic",
        "object",
        "base-from-own-package",
        "own-package-imported-whole",
        "relative-import",
        "base-in-this-module",
        "base-assigned-in-this-module",
        "bases-in-a-circle",
        "dataclass-under-abc",
        "dataclass-under-an-outside-base",
        "family-base-of-nuikit",
    ],
)
def test_a_class_of_the_project_has_no_hand_written_init(source, expected):
    assert rules_in_demo(source) == expected


def test_a_long_line_of_classes_passes_on_that_it_comes_from_outside():
    line = "".join(f"class C{i}(C{i - 1}): ...\n" for i in range(1, 1500))
    source = f"import logging\nclass C0(logging.Handler): ...\n{line}"

    assert rules_in_demo(f"{source}class Last(C1499):\n{INIT}") == []
    assert rules_in_demo(f"{source}class Last(C1500):\n{INIT}") == [(1503, "TYP-4")]


def test_the_packages_under_src_are_the_projects_own(opted_in):
    for name in ("demo", "tools"):
        (opted_in / "src" / name).mkdir(parents=True)
        (opted_in / "src" / name / "__init__.py").touch()
    (opted_in / "tests").mkdir()
    module = opted_in / "src" / "demo" / "runner.py"
    module.write_text(
        "import logging\n\nfrom demo.base import Endpoint\n"
        "from tools.base import Tool\n"
        f"\n\nclass Api(Endpoint):\n{INIT}"
        f"\n\nclass Hammer(Tool):\n{INIT}"
        f"\n\nclass Quiet(logging.Handler):\n{INIT}"
    )
    fake = opted_in / "tests" / "fakes.py"
    fake.write_text(
        "import httpx\n\nfrom demo.base import Endpoint\n"
        f"\n\nclass Scripted(Endpoint):\n{INIT}"
        f"\n\nclass Replay(httpx.BaseTransport):\n{INIT}"
    )

    assert rules_of(module) == [(8, "TYP-4"), (12, "TYP-4")]
    assert rules_of(fake) == [(7, "TYP-4")]


def test_the_top_package_of_a_file_is_the_projects_own_without_a_src_folder(tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").touch()
    module = tmp_path / "demo" / "runner.py"
    module.write_text(
        "import logging\n\nfrom demo.base import Endpoint\n"
        f"\n\nclass Api(Endpoint):\n{INIT}"
        f"\n\nclass Quiet(logging.Handler):\n{INIT}"
    )

    assert rules_of(module) == [(7, "TYP-4")]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import dataclasses\n\nrow = dataclasses.asdict(arguments)\n", []),
        ("from dataclasses import asdict, fields, is_dataclass, replace\n", []),
        ("from dataclasses import field\n", [(1, "TYP-4")]),
        ("from dataclasses import asdict, make_dataclass\n", [(1, "TYP-4")]),
        (
            "import dataclasses\n\n\n@dataclasses.dataclass\nclass A:\n    x: int\n",
            [(4, "TYP-4")],
        ),
        (
            "import dataclasses\n\n\n@dataclasses.dataclass(frozen=True)\n"
            "class A:\n    x: int\n",
            [(4, "TYP-4")],
        ),
        (
            "import dataclasses\n\n"
            "Row = dataclasses.make_dataclass('Row', [('name', str)])\n",
            [(3, "TYP-4")],
        ),
        (
            "import dataclasses\n\n\n@define\nclass Row:\n"
            "    names: list[str] = dataclasses.field(default_factory=list)\n",
            [(6, "TYP-4")],
        ),
        (
            "import dataclasses as dc\n\n"
            "Row = dc.make_dataclass('Row', [('name', str)])\n",
            [(3, "TYP-4")],
        ),
        (
            "import dataclasses\n\n\n@dataclasses.dataclass\nclass A:\n"
            "    x: list[int] = dataclasses.field(default_factory=list)\n",
            [(4, "TYP-4")],
        ),
        (
            "import dataclasses\n\n\n"
            "@dataclasses.dataclass  # conventions: TYP-4 - HfArgumentParser reads "
            "dataclasses.\nclass A:\n"
            "    x: list[int] = dataclasses.field(default_factory=list)\n",
            [],
        ),
        (
            "from dataclasses import dataclass, field\n\n\n@dataclass\nclass A:\n"
            "    x: list[int] = field(default_factory=list)\n",
            [(4, "TYP-4")],
        ),
        (
            "from dataclasses import dataclass\nimport dataclasses\n\n"
            "Row = dataclasses.make_dataclass('Row', [('name', str)])\n",
            [(4, "TYP-4")],
        ),
        (
            "from dataclasses import dataclass\n\n\n"
            "@dataclass  # conventions: TYP-4 - HfArgumentParser reads dataclasses.\n"
            "class Arguments:\n    seed: int\n",
            [],
        ),
        (
            "from dataclasses import dataclass\n\n\n@dataclass\n"
            "class LoadError(Exception):\n    path: str\n",
            [(1, "TYP-4")],
        ),
    ],
    ids=[
        "module-read-for-asdict",
        "readers-of-a-dataclass",
        "field",
        "make-dataclass-among-readers",
        "dotted-decorator",
        "dotted-decorator-called",
        "make-dataclass-on-the-module",
        "field-on-the-module",
        "make-dataclass-on-an-alias",
        "field-of-a-decorated-class",
        "field-of-a-waived-class",
        "import-of-a-decorated-class",
        "import-of-a-made-class",
        "import-of-a-waived-class",
        "import-of-an-exception",
    ],
)
def test_only_what_defines_a_dataclass_is_reported(source, expected):
    assert rules(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        (
            "from torch import Tensor, nn\n\n\nclass Perceptron(nn.Module):\n"
            "    def forward(self, x: Tensor) -> Tensor: ...\n"
        ),
        "import torch\n\n\n@torch.no_grad()\ndef evaluate(model): ...\n",
        "from torch.utils.data import Dataset\n\n\nclass Rows(Dataset[int]): ...\n",
        (
            "import torch\n\n\nclass Scorer:\n    @torch.no_grad()\n"
            "    def score(self): ...\n"
        ),
        "import torch.nn as nn\n\nif FAST:\n\n    class Head(nn.Module): ...\n",
        (
            "try:\n    import torch\nexcept ImportError:\n    torch = None\n\n\n"
            "@torch.jit.script\nclass Pair: ...\n"
        ),
    ],
    ids=[
        "class-base",
        "function-decorator",
        "subscripted-base",
        "method-decorator",
        "class-under-if",
        "import-under-try",
    ],
)
def test_a_heavy_import_stays_at_the_top_when_the_module_needs_it_at_import(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import torch\n\nSEED = torch.manual_seed(0)\n", [(1, "ARC-8")]),
        (
            "import torch\n\n\ndef zeros(n, *, device=torch.device('cpu')): ...\n",
            [(1, "ARC-8")],
        ),
        (
            "import wandb\nfrom torch import nn\n\n\nclass Head(nn.Module): ...\n\n\n"
            "def track():\n    wandb.init()\n",
            [(1, "ARC-8")],
        ),
        (
            "import torch\n\n\ndef build():\n    class Head(torch.nn.Module): ...\n\n"
            "    return Head()\n",
            [(1, "ARC-8")],
        ),
        (
            "import torch\n\n\ndef build():\n    @torch.no_grad()\n"
            "    def inner(): ...\n\n    return inner\n",
            [(1, "ARC-8")],
        ),
    ],
    ids=[
        "constant",
        "default-value",
        "another-heavy-module",
        "base-of-a-class-inside-a-function",
        "decorator-inside-a-function",
    ],
)
def test_a_heavy_import_used_only_when_code_runs_is_reported(source, expected):
    assert rules(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "try:\n    import wandb\nexcept ImportError:\n    wandb = None\n",
            [(2, "ARC-8")],
        ),
        (
            "try:\n    import fast\nexcept ImportError:\n    import torch\n",
            [(4, "ARC-8")],
        ),
        (
            "try:\n    import fast\nexcept ImportError:\n    fast = None\n"
            "else:\n    import jax\nfinally:\n    import wandb\n",
            [(6, "ARC-8"), (8, "ARC-8")],
        ),
        ("if importlib.util.find_spec('jax'):\n    import jax\n", [(2, "ARC-8")]),
        ("if FAST:\n    import fast\nelif SLOW:\n    import torch\n", [(4, "ARC-8")]),
        ("with suppress(ImportError):\n    import wandb\n", [(2, "ARC-8")]),
        (
            "try:\n    if FAST:\n        with suppress(ImportError):\n"
            "            import torch\nexcept OSError:\n    pass\n",
            [(4, "ARC-8")],
        ),
        (
            "if TYPE_CHECKING:\n    from torch import nn\nelse:\n    import torch\n",
            [(4, "ARC-8")],
        ),
        (
            "if not TYPE_CHECKING:\n    import jax\nelse:\n    from torch import nn\n",
            [(2, "ARC-8")],
        ),
        (
            "if __name__ == '__main__':\n    pass\nelse:\n    import torch\n",
            [(4, "ARC-8")],
        ),
        ("if __name__ != '__main__':\n    import torch\n", [(2, "ARC-8")]),
    ],
    ids=[
        "try",
        "except",
        "else-and-finally",
        "if",
        "elif",
        "with",
        "nested-blocks",
        "else-of-type-checking",
        "not-type-checking",
        "else-of-main-guard",
        "not-main",
    ],
)
def test_a_heavy_import_in_a_block_of_the_module_is_reported(source, expected):
    assert rules(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "import typing\n\nif typing.TYPE_CHECKING:\n    import torch\n",
        "if TYPE_CHECKING:\n    try:\n        import torch\n    except ImportError:\n"
        "        pass\n",
        "def load():\n    try:\n        import wandb\n    except ImportError:\n"
        "        return None\n    return wandb\n",
        "class Lazy:\n    try:\n        import wandb\n    except ImportError:\n"
        "        wandb = None\n",
        "if __name__ == '__main__':\n    import torch\n\n    main()\n",
        "if '__main__' == __name__:\n    try:\n        import wandb\n"
        "    except ImportError:\n        pass\n",
    ],
    ids=[
        "dotted-type-checking",
        "try-under-type-checking",
        "try-inside-a-function",
        "try-inside-a-class",
        "main-guard",
        "main-guard-reversed",
    ],
)
def test_a_heavy_import_outside_the_blocks_of_the_module_passes(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    "source",
    [
        (
            "class UTC(logging.Formatter):\n    @override\n"
            "    def formatTime(self, record, datefmt=None): ...\n"
        ),
        "class A(B):\n    @typing.override\n    def fit(self, x, y=None): ...\n",
        (
            "class A(B):\n    @typing_extensions.override\n"
            "    async def fit(self, x, y=None): ...\n"
        ),
        "class Zeros(io.RawIOBase):\n    def read(self, size=-1, /): ...\n",
    ],
    ids=[
        "override",
        "typing-override",
        "typing-extensions-override",
        "positional-only",
    ],
)
def test_a_signature_fixed_elsewhere_keeps_its_positional_defaults(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    ("source", "named"),
    [
        ("def f(a=1, /, b=2): ...\n", ["b"]),
        ("def f(a, b=1, /, c=2, d=3, *, e=4): ...\n", ["c", "d"]),
        ("@cache\ndef f(a, b=1): ...\n", ["b"]),
        ("@overrides\ndef f(a, b=1): ...\n", ["b"]),
    ],
    ids=[
        "after-the-slash",
        "between-slash-and-star",
        "another-decorator",
        "decorator-of-another-name",
    ],
)
def test_a_positional_default_is_reported_where_the_caller_may_name_it(source, named):
    found = check_source(source, path=PACKAGE)

    assert [(f.rule, re.findall(r"`(\w+)`", f.message)) for f in found] == [
        ("STY-4", named)
    ]


@pytest.mark.parametrize(
    "source",
    [
        "names = [p.name for p in ps if p.kind == inspect.Parameter.KEYWORD_ONLY]\n",
        "if values.dtype.kind != 'f':\n    pass\n",
        "if values.dtype.kind in ('f', 'c'):\n    pass\n",
        "same = a.kind == b.kind\n",
        "if item.kind in KINDS:\n    pass\n",
        "if item.kind == f'{prefix}-api':\n    pass\n",
        "if item.kind is None or item.kind > 'api':\n    pass\n",
        "match values.dtype.kind:\n    case 'f' | 'c':\n        pass\n",
        "match item.kind:\n    case Kind.API | 'f':\n        pass\n",
        "match item:\n    case 'api':\n        pass\n",
        "if values.dtype.kind in 'iu':\n    pass\n",
        "if values.dtype.kind not in 'fc':\n    pass\n",
        "if 'api' in item.kind:\n    pass\n",
    ],
    ids=[
        "inspect-parameter-kind",
        "dtype-kind",
        "dtype-kind-in-letters",
        "kind-with-kind",
        "kind-in-a-named-collection",
        "kind-with-an-f-string",
        "kind-ordered-or-none",
        "match-on-dtype-kind",
        "match-on-enum-members",
        "match-on-another-subject",
        "dtype-kind-in-a-string",
        "dtype-kind-not-in-a-string",
        "substring-of-a-kind",
    ],
)
def test_a_kind_that_is_no_family_kind_may_be_compared(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "if item.kind != 'api':\n    pass\n",
        "if 'api' == item.kind:\n    pass\n",
        "if item.kind in ('api', 'batch'):\n    pass\n",
        "if item.kind not in ['api']:\n    pass\n",
        "if item.kind in {'f', 'batch'}:\n    pass\n",
        "if 0 < item.cost and item.kind == 'api' != other:\n    pass\n",
        "match item.kind:\n    case 'api':\n        pass\n    case _:\n        pass\n",
        "match self.config.kind:\n    case 'api' | 'batch':\n        pass\n",
        "match item.kind:\n    case 'api' | 'batch' as remote:\n        pass\n",
    ],
    ids=[
        "not-equal",
        "string-first",
        "in-a-tuple",
        "not-in-a-list",
        "in-a-set-with-a-letter",
        "inside-a-chain",
        "match",
        "match-or-pattern",
        "match-capture",
    ],
)
def test_a_kind_attribute_set_against_a_string_is_reported_once(source):
    assert rules(source) == [(1, "ARC-4")]
    assert rules(source, "tests/demo/test_runner.py") == []


@pytest.mark.parametrize(
    "source",
    [
        "os.environ['TOKENIZERS_PARALLELISM'] = 'false'\n",
        "os.environ['PATH'] += ':/opt/bin'\n",
        "del os.environ['TOKEN']\n",
        "os.environ.setdefault('SEED', '0')\n",
        "os.environ.update(SEED='0')\n",
        "os.environ.pop('TOKEN', None)\n",
        "os.environ.clear()\n",
        "env = os.environ.copy()\n",
        "env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(gpu)}\n",
        "env = dict(os.environ)\n",
        "subprocess.run(command, env=os.environ, check=True)\n",
    ],
    ids=[
        "assign",
        "append",
        "delete",
        "setdefault",
        "update",
        "pop",
        "clear",
        "copy",
        "unpacked-into-a-dict",
        "dict-of-it",
        "handed-to-a-child",
    ],
)
def test_setting_a_variable_or_handing_the_environment_on_is_no_read(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("token = os.getenv('TOKEN')\n", [(1, "ENV-3")]),
        ("token = os.environ.get('TOKEN', '')\n", [(1, "ENV-3")]),
        ("if 'TOKEN' in os.environ:\n    pass\n", [(1, "ENV-3")]),
        ("if 'TOKEN' not in os.environ:\n    pass\n", [(1, "ENV-3")]),
        ("os.environ['COPY'] = os.environ['TOKEN']\n", [(1, "ENV-3")]),
        ("found = (\n    'TOKEN'\n    in os.environ\n)\n", [(3, "ENV-3")]),
    ],
    ids=[
        "getenv",
        "get",
        "in",
        "not-in",
        "read-into-another-variable",
        "reported-at-the-line-of-os-environ",
    ],
)
def test_reading_a_variable_is_reported(source, expected):
    assert rules(source) == expected
    assert rules(source, "src/demo/paths.py") == []


@pytest.mark.parametrize(
    "source",
    [
        "raise FileNotFoundError('Makefile')\n",
        "raise KeyError('Missing.')\n",
        "raise ValueError('None is not a seed')\n",
        "raise ValueError('True: expected a count')\n",
        "raise ValueError('HTTP status 500')\n",
        "raise ConfigError('OmegaConf cannot resolve it')\n",
        "raise ValueError('X and y differ in length')\n",
        "raise ValueError('F-score needs one positive label')\n",
        "raise ValueError('Content-Type header is missing')\n",
        "raise ValueError('`Trainer` needs a seed')\n",
        "raise ValueError(\"'Makefile' has no target\")\n",
        "raise ValueError('Trainer.fit was not called')\n",
        "raise TimeoutError('still waiting...')\n",
    ],
    ids=[
        "one-word-is-a-name",
        "one-word-with-a-period",
        "none",
        "true-with-a-colon",
        "acronym",
        "mixed-case",
        "one-letter-name",
        "one-letter-name-with-a-hyphen",
        "mixed-case-with-a-hyphen",
        "name-in-backticks",
        "name-in-quotes",
        "dotted-name",
        "ellipsis",
    ],
)
def test_a_message_that_opens_with_a_name_or_trails_off_passes(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "raise ValueError('A table needs at least one row')\n",
        'raise ValueError("Can\'t read a negative number of rows")\n',
        "raise ValueError('Rows: expected fewer than ten')\n",
        "raise UserError(f'Missing, {name}')\n",
        "raise ValueError('Non-empty table expected')\n",
        "raise ValueError('wait a second.')\n",
    ],
    ids=["article", "apostrophe", "colon", "comma", "hyphen", "period"],
)
def test_a_capitalised_first_word_or_a_period_is_reported(source):
    assert rules(source) == [(1, "ERR-3")]


@pytest.mark.parametrize(
    "source",
    [
        "_log.info(f'started on {port}')\n",
        "LOG.info('started on {}'.format(port))\n",
        "_logger.warning('Proxy started')\n",
        "LOGGER.info('Proxy started on %s', port)\n",
        "self._log.error('Proxy failed')\n",
        "logging.info('Proxy started on %s' % port)\n",
        "logging.warning(f'started on {port}')\n",
    ],
    ids=[
        "private-log",
        "upper-log",
        "private-logger",
        "upper-logger",
        "private-attribute",
        "logging-function",
        "logging-function-f-string",
    ],
)
def test_an_event_is_checked_on_a_logger_under_its_usual_names(source):
    assert rules(source) == [(1, "LOG-2")]


@pytest.mark.parametrize(
    "source",
    [
        "_log.info('proxy_started', port=8000)\n",
        "logging.info('proxy_started')\n",
        "catalog.info('Proxy started')\n",
        "logging.getLogger('Proxy started')\n",
    ],
    ids=["private-log", "logging-function", "another-receiver", "another-function"],
)
def test_a_snake_case_event_or_a_call_that_logs_nothing_passes(source):
    assert rules(source) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "class SummaryTests(unittest.TestCase):\n    def test_empty(self): ...\n",
            [(1, "TST-1")],
        ),
        ("class Summary(IsolatedAsyncioTestCase):\n    x = 1\n", [(1, "TST-1")]),
        ("class Summary:\n    async def test_empty(self): ...\n", [(1, "TST-1")]),
        ("@define\nclass TestClock:\n    now_s: float = 0.0\n", []),
        ("class Scripted:\n    def reply(self): ...\n", []),
    ],
    ids=[
        "testcase-under-another-name",
        "testcase-base-alone",
        "test-method-alone",
        "fake-named-test",
        "fake-with-methods",
    ],
)
def test_a_class_is_a_test_class_by_what_it_holds(source, expected):
    assert rules(source, "tests/conftest.py") == expected


@pytest.mark.parametrize(
    ("path", "quoted"),
    [
        ("src/demo/_utils.py", "_utils"),
        ("src/demo/__helpers.py", "__helpers"),
        ("src/demo/string_utils.py", "string_utils"),
        ("src/demo/text_util.py", "text_util"),
        ("src/demo/io_helpers/text.py", "io_helpers"),
        ("src/demo/data_common.py", "data_common"),
        ("src/nlp_common/_utils.py", "_utils"),
    ],
    ids=[
        "private",
        "dunder-private",
        "utils-suffix",
        "util-suffix",
        "helpers-folder",
        "common-suffix",
        "under-a-suffixed-package",
    ],
)
def test_a_grab_bag_is_reported_under_its_private_and_suffixed_names(path, quoted):
    found = check_source("x = 1\n", path=path)

    assert [(f.line, f.rule) for f in found] == [(1, "LAY-2")]
    assert found[0].message.startswith(f"`{quoted}` is a grab-bag module")


@pytest.mark.parametrize(
    "path",
    [
        "src/demo/utilities.py",
        "src/demo/shared.py",
        "src/demo/futils.py",
        "src/demo/core_ops.py",
        "src/demo/_rows.py",
        "scripts/_utils.py",
        "src/nlp_common/tokenize_corpus.py",
    ],
    ids=[
        "utilities",
        "shared",
        "no-underscore-before-suffix",
        "prefix-not-suffix",
        "private-one-thing",
        "outside-src",
        "suffixed-top-package",
    ],
)
def test_a_module_named_after_one_thing_is_no_grab_bag(path):
    assert rules("x = 1\n", path) == []


@pytest.mark.parametrize(
    ("waiver", "statement", "path", "unwaived"),
    [
        (
            "# conventions: STY-4 - OmegaConf passes resolver arguments by position.\n",
            "def env_or(\n"
            '    variable: str, default: str = "", separator: str = ","\n'
            ") -> str:\n"
            "    return separator.join([variable, default])\n",
            PACKAGE,
            [(2, "STY-4")],
        ),
        (
            "# conventions: TST-1 - pytest-benchmark groups rounds by class.\n",
            "@pytest.mark.slow\n"
            "class TestThroughput:\n"
            "    def test_reads_a_thousand_rows_a_second(self): ...\n",
            "tests/test_throughput.py",
            [(2, "TST-1")],
        ),
        (
            "# conventions: STY-4 - OmegaConf passes resolver arguments by position,\n"
            "# and a second line finishes the reason.\n",
            'def env_or(variable: str, default: str = "") -> str:\n'
            "    return variable or default\n",
            PACKAGE,
            [(1, "STY-4")],
        ),
        (
            "# conventions: ENV-3 - this module runs before paths.py is imported.\n",
            "CACHE = Path(\n"
            "    'downloads',\n"
            "    os.environ.get('ACME_CACHE', '.cache'),\n"
            ")\n",
            PACKAGE,
            [(3, "ENV-3")],
        ),
        (
            "# conventions: ENV-1, ENV-3 - this module runs before paths.py.\n",
            "CACHE = Path(os.environ.get('CACHE', Path(__file__).parent.parent))\n",
            PACKAGE,
            [(1, "ENV-1"), (1, "ENV-3")],
        ),
    ],
    ids=[
        "wrapped-signature",
        "decorated-class",
        "reason-on-two-lines",
        "wrapped-assignment",
        "two-rules",
    ],
)
def test_a_waiver_alone_above_a_statement_covers_it_up_to_its_body(
    waiver, statement, path, unwaived
):
    assert rules(statement, path) == unwaived
    assert rules(waiver + statement, path) == []


def test_a_waiver_above_a_function_does_not_cover_its_body():
    source = (
        "# conventions: ENV-3 - the name is all this function knows.\n"
        "def token(\n"
        "    name: str,\n"
        ") -> str:\n"
        "    return os.environ[name]\n"
    )

    assert rules(source) == [(5, "ENV-3")]

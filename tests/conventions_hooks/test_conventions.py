"""The convention checker flags the code rules an AST can decide, and only those."""

from __future__ import annotations

import json

import pytest

from conventions_hooks.conventions import check_file, check_source, claude_hook, main

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


SHOTGUN = """
def start(cfg):
    if cfg.backend == "modal":
        launch_modal()
    elif cfg.backend == "local":
        launch_local()


def cost(cfg):
    if cfg.backend == "modal":
        return price_modal()
    return 0.0
"""

LONG_CHAIN = """
def score(pred, gold, *, metric):
    if metric == "f1":
        return f1(pred, gold)
    elif metric == "em":
        return exact(pred, gold)
    elif metric == "bleu":
        return bleu(pred, gold)
    raise UnknownMetricError(metric)
"""

GUARDS = """
def render(rows, *, fmt):
    if fmt == "csv":
        return to_csv(rows)
    if fmt == "json":
        return to_json(rows)
    if fmt == "md":
        return to_markdown(rows)
    raise UnknownFormatError(fmt)
"""

CONSTANTS = """
def fraction(split):
    match split:
        case "train":
            return 0.8
        case "val":
            return 0.1
        case "test":
            return 0.1
"""


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (SHOTGUN, [(10, "ARC-9")]),
        (LONG_CHAIN, [(3, "ARC-9")]),
        (GUARDS, [(3, "ARC-9")]),
        (CONSTANTS, [(3, "ARC-9")]),
    ],
    ids=[
        "same-variant-in-two-functions",
        "three-arms-run-code",
        "three-guard-clauses",
        "three-arms-map-constants",
    ],
)
def test_switches_on_a_variant_name_are_reported(source, expected):
    assert rules(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # The factory: every arm builds and returns an object.
        "def build(name):\n"
        "    if name == 'a':\n        return A()\n"
        "    elif name == 'b':\n        return B()\n"
        "    elif name == 'c':\n        return C()\n",
        # A closed set that gains operations stays a match ending in `assert_never`.
        "def describe(shape):\n    match shape.form:\n"
        "        case 'circle':\n            draw()\n"
        "        case 'square':\n            fill()\n"
        "        case 'line':\n            stroke()\n"
        "        case _:\n            assert_never(shape.form)\n",
        # Two arms in one function, different variant names elsewhere.
        "def a(x):\n    if x.mode == 'fast':\n        go()\n\n\n"
        "def b(x):\n    if x.split == 'fast':\n        go()\n",
        "if __name__ == '__main__':\n    main()\n",
    ],
    ids=["factory", "closed-match", "different-names", "main-guard"],
)
def test_one_switch_in_one_place_passes(source):
    assert rules(source) == []


def test_tests_may_switch_on_variants():
    assert rules(LONG_CHAIN, "tests/demo/test_metrics.py") == []


def package(root, files: dict[str, str]):
    """Write `files` under `root/src/demo/`, each folder a package; return it."""
    folder = root / "src" / "demo"
    for name, source in {"__init__.py": "", **files}.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        (path.parent / "__init__.py").touch()
        path.write_text(source)
    return folder


START = (
    "def start(cfg):\n"
    "    if cfg.backend == 'modal':\n        launch()\n"
    "    elif cfg.backend == 'local':\n        run()\n"
)
COST = "def cost(cfg):\n    if cfg.backend == 'modal':\n        return bill()\n"


def test_a_variant_switched_on_in_two_modules_is_reported_in_each(tmp_path):
    demo = package(tmp_path, {"start.py": START, "billing/cost.py": COST})

    start = [(f.line, f.rule, f.message) for f in check_file(demo / "start.py")]
    cost = [(f.line, f.rule) for f in check_file(demo / "billing" / "cost.py")]

    assert [(line, rule) for line, rule, _ in start] == [(2, "ARC-9")]
    assert "demo/billing/cost.py:2" in start[0][2]
    assert cost == [(2, "ARC-9")]


@pytest.mark.parametrize(
    "files",
    [
        # A lone test in each module is not a switch.
        {"a.py": "def a(p):\n    if p.suffix == '.py':\n        go()\n", "b.py": COST},
        {
            "a.py": "def a(p):\n    if p.backend == 'modal':\n        go()\n",
            "b.py": COST,
        },
        # The factory may switch on what the rest of the package uses.
        {
            "a.py": "def build(cfg):\n"
            "    if cfg.backend == 'modal':\n        return Modal()\n"
            "    elif cfg.backend == 'local':\n        return Local()\n",
            "b.py": COST,
        },
    ],
    ids=["one-arm-tests", "one-arm-each", "factory"],
)
def test_switches_across_modules_that_are_not_repeats_pass(tmp_path, files):
    demo = package(tmp_path, files)

    assert [f for f in check_file(demo / "a.py") if f.rule == "ARC-9"] == []


def test_a_module_outside_a_package_is_checked_alone(tmp_path):
    (tmp_path / "start.py").write_text(START)
    (tmp_path / "cost.py").write_text(COST)

    assert check_file(tmp_path / "start.py") == []


@pytest.mark.parametrize(
    "source",
    [
        "from demo.store import save\n\n\ndef persist(item, *, force):\n"
        "    return save(item, force=force)\n",
        "from . import store\n\n\ndef persist(*args, **kwargs):\n"
        "    store.save(*args, **kwargs)\n",
        "def _save(item):\n    ...\n\n\ndef persist(item):\n"
        '    """Persist one item."""\n    return _do(item)\n\n\n'
        "def _persist(item):\n    return _save(item)\n",
    ],
    ids=["keywords", "star-arguments", "private-to-private"],
)
def test_a_function_that_only_forwards_is_reported(tmp_path, source):
    demo = package(tmp_path, {"api.py": source})

    found = [(f.rule, f.message) for f in check_file(demo / "api.py")]

    assert [rule for rule, _ in found] == ["ARC-10"]


@pytest.mark.parametrize(
    "source",
    [
        # Changes or adds an argument: it hides something.
        "from demo.store import save\n\n\ndef persist(item):\n"
        "    return save(item, force=True)\n",
        "from demo.store import save\n\n\ndef persist(item, path):\n"
        "    return save(path, item)\n",
        # Calls outside the package: an adapter over a dependency.
        "import yaml\n\n\ndef load(text):\n    return yaml.safe_load(text)\n",
        # A public name over a private implementation is the interface.
        "def _save(item):\n    ...\n\n\ndef save(item):\n    return _save(item)\n",
        # Registrations and methods are left alone.
        "from demo.store import save\n\n\n@app.command()\ndef persist(item):\n"
        "    return save(item)\n",
        "from demo.store import save\n\n\nclass Store:\n"
        "    def persist(self, item):\n        return save(item)\n",
        "from demo.store import save\n\n\n"
        "def persist(item):  # conventions: ARC-10 - the public name of `save`.\n"
        "    return save(item)\n",
    ],
    ids=[
        "adds-argument",
        "reorders",
        "third-party",
        "private-implementation",
        "decorated",
        "method",
        "allowed",
    ],
)
def test_a_function_that_does_more_than_forward_passes(tmp_path, source):
    demo = package(tmp_path, {"api.py": source})

    assert check_file(demo / "api.py") == []

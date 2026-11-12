"""The checks that look past one file read the right modules of its package."""

from __future__ import annotations

import json
from pathlib import Path, PurePath

import pytest

from conventions_hooks import package
from conventions_hooks.conventions import check_file, claude_hook

START = (
    "def start(cfg):\n"
    "    if cfg.backend == 'modal':\n        launch()\n"
    "    elif cfg.backend == 'local':\n        run()\n"
)
COST = "def cost(cfg):\n    if cfg.backend == 'modal':\n        return bill()\n"
CLOSED = (
    "def {name}(fmt):\n    match fmt:\n"
    "        case 'console':\n            return {name}_console()\n"
    "        case 'json':\n            return {name}_json()\n"
    "        case _:\n            assert_never(fmt)\n"
)


def rules(path: Path) -> list[tuple[int, str]]:
    return [(f.line, f.rule) for f in check_file(path)]


def test_the_top_package_is_the_outermost_folder_with_an_init(demo_package):
    demo = demo_package({"billing/cost.py": COST})

    assert package.top_package(demo / "billing" / "cost.py") == demo.resolve()
    assert package.top_package(demo.parent / "script.py") is None


def test_a_variant_switched_on_in_two_modules_is_reported_in_each(demo_package):
    demo = demo_package({"start.py": START, "billing/cost.py": COST})

    assert rules(demo / "start.py") == [(2, "ARC-9")]
    assert rules(demo / "billing" / "cost.py") == [(2, "ARC-9")]


def test_the_other_module_is_written_the_way_the_checked_file_was(
    demo_package, tmp_path, monkeypatch
):
    demo = demo_package({"start.py": START, "billing/cost.py": COST})
    monkeypatch.chdir(tmp_path)

    relative = check_file(Path("src/demo/start.py"))
    absolute = check_file(demo / "start.py")

    assert "`cost` (src/demo/billing/cost.py:2)" in relative[0].message
    assert f"`cost` ({demo / 'billing' / 'cost.py'}:2)" in absolute[0].message


@pytest.mark.parametrize(
    "files",
    [
        # A lone test in each module is not a switch.
        {"a.py": "def a(p):\n    if p.suffix == '.py':\n        go()\n", "b.py": COST},
        {
            "a.py": "def a(p):\n    if p.backend == 'modal':\n        go()\n",
            "b.py": COST,
        },
        # Each operation over a closed set is one more match ending in `assert_never`.
        {
            "a.py": CLOSED.format(name="renderer"),
            "b.py": CLOSED.format(name="coloured"),
        },
    ],
    ids=["one-arm-tests", "one-arm-each", "closed-match-in-each"],
)
def test_switches_across_modules_that_are_not_repeats_pass(demo_package, files):
    demo = demo_package(files)

    assert rules(demo / "a.py") == []


@pytest.mark.parametrize(
    "factory",
    [
        "def build(cfg):\n"
        "    if cfg.backend == 'modal':\n        return Modal()\n"
        "    elif cfg.backend == 'local':\n        return Local()\n",
        # The factory may build through classmethod constructors.
        "def build(cfg):\n"
        "    if cfg.backend == 'modal':\n        return Modal.from_config(cfg)\n"
        "    elif cfg.backend == 'local':\n        return Local.from_config(cfg)\n",
        # A factory of one arm counts, though a lone test elsewhere does not.
        "def build(cfg):\n    return Modal() if cfg.backend == 'modal' else Local()\n",
    ],
    ids=[
        "factory",
        "factory-through-classmethods",
        "factory-as-conditional-expression",
    ],
)
def test_a_function_on_a_value_of_a_factory_in_another_module_is_reported(
    demo_package, factory
):
    demo = demo_package({"a.py": factory, "b.py": COST})

    assert (rules(demo / "a.py"), rules(demo / "b.py")) == ([], [(2, "ARC-9")])


def test_a_module_outside_a_package_is_checked_alone(tmp_path):
    (tmp_path / "start.py").write_text(START)
    (tmp_path / "cost.py").write_text(COST)

    assert check_file(tmp_path / "start.py") == []


def test_tests_and_folders_that_are_not_packages_do_not_count(demo_package):
    demo = demo_package({"cost.py": COST, "tests/test_start.py": START})
    for stray in ("data/start.py", ".venv/lib/site/start.py"):
        (demo / stray).parent.mkdir(parents=True)
        (demo / stray).write_text(START)

    assert rules(demo / "cost.py") == []


def test_a_module_that_cannot_be_read_is_skipped(demo_package):
    demo = demo_package({"start.py": START, "cost.py": COST, "broken.py": "def (:\n"})
    (demo / ".#start.py").symlink_to("nobody@nowhere.1")
    (demo / "binary.py").write_bytes(b"\xff\xfe\x00")

    assert rules(demo / "cost.py") == [(2, "ARC-9")]


@pytest.mark.parametrize(
    "data",
    [b"# coding: hex\nx = 1\n", b"x = " + b"-" * 20_000 + b"1\n"],
    ids=["codec-that-is-no-text-encoding", "too-deep-to-parse"],
)
def test_a_module_python_cannot_read_does_not_stop_the_check(demo_package, data):
    demo = demo_package({"start.py": START, "cost.py": COST})
    (demo / "odd.py").write_bytes(data)

    assert rules(demo / "cost.py") == [(2, "ARC-9")]


def test_the_other_modules_are_read_the_way_python_reads_them(demo_package):
    demo = demo_package({"cost.py": COST})
    (demo / "start.py").write_bytes(b"\xef\xbb\xbf" + START.encode())

    assert rules(demo / "cost.py") == [(2, "ARC-9")]


def test_a_waived_switch_does_not_count_against_the_other_modules(demo_package):
    waiver = "    # conventions: ARC-9 - the launcher alone knows every backend.\n"
    waived = START.replace("    if cfg", waiver + "    if cfg", 1)
    demo = demo_package({"start.py": waived, "cost.py": COST})

    assert (rules(demo / "start.py"), rules(demo / "cost.py")) == ([], [])


def test_a_module_changed_since_the_last_check_is_read_again(demo_package):
    demo = demo_package({"start.py": START, "cost.py": COST})

    before = rules(demo / "cost.py")
    (demo / "start.py").write_text("def start(cfg):\n    launch(cfg)\n")
    after = rules(demo / "cost.py")

    assert (before, after) == ([(2, "ARC-9")], [])


def test_the_claude_hook_reports_a_switch_repeated_in_another_module(
    opted_in, demo_package, capsys
):
    demo = demo_package({"start.py": START, "cost.py": COST})
    payload = json.dumps({"tool_input": {"file_path": str(demo / "cost.py")}})

    assert claude_hook(payload) == 2
    assert f"{demo / 'start.py'}:2" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tests/test_runner.py", True),
        ("tests/demo/fakes.py", True),
        ("src/demo/tests/helpers.py", True),
        ("test_runner.py", True),
        ("conftest.py", True),
        ("scripts/test_gpu.py", True),
        ("src/demo/test_selection.py", False),
        ("src/demo/conftest.py", False),
        ("src/demo/selection.py", False),
        ("scripts/train_once.py", False),
    ],
    ids=[
        "under-tests",
        "helper-under-tests",
        "tests-folder-inside-the-package",
        "pytest-file",
        "conftest",
        "pytest-file-in-scripts",
        "test-name-under-src",
        "conftest-under-src",
        "module",
        "script",
    ],
)
def test_a_file_under_src_is_package_code_whatever_its_name(path, expected):
    assert package.is_test(PurePath(path)) is expected


def test_a_module_named_like_a_test_gets_the_rules_of_its_package(
    opted_in, demo_package
):
    selection = (
        "import os\n\n\n"
        "def chosen(task, limit=10):\n"
        "    if task.kind == 'api':\n        return []\n"
        "    return os.environ['TESTS'].split(',')[:limit]\n\n\n"
        "class TestPlan:\n    steps = 3\n"
    )
    demo = demo_package({"paths.py": "", "test_selection.py": selection})

    assert rules(demo / "test_selection.py") == [
        (4, "STY-4"),
        (5, "ARC-4"),
        (7, "ENV-3"),
    ]


@pytest.mark.parametrize("name", ["test_launch.py", "conftest.py"])
def test_the_switches_of_a_module_named_like_a_test_count_under_src(
    opted_in, demo_package, name
):
    demo = demo_package({"cost.py": COST, name: START})

    assert rules(demo / "cost.py") == [(2, "ARC-9")]


def test_the_pytest_files_of_a_package_outside_src_do_not_count(opted_in):
    flat = opted_in / "demo"
    flat.mkdir()
    for name, source in {"__init__.py": "", "cost.py": COST, "launch.py": ""}.items():
        (flat / name).write_text(source)
    for name in ("test_launch.py", "conftest.py"):
        (flat / name).write_text(START)

    before = rules(flat / "cost.py")
    (flat / "launch.py").write_text(START)
    after = rules(flat / "cost.py")

    assert (before, after) == ([], [(2, "ARC-9")])


@pytest.mark.parametrize(
    ("above", "other", "expected"),
    [("src", "test_launch.py", []), ("tests", "launch.py", [(2, "ARC-9")])],
    ids=["src-above", "tests-above"],
)
def test_a_folder_above_a_package_without_a_project_decides_nothing(
    tmp_path, monkeypatch, above, other, expected
):
    flat = tmp_path / above / "proj" / "demo"
    flat.mkdir(parents=True)
    for name, source in {"__init__.py": "", "cost.py": COST, other: START}.items():
        (flat / name).write_text(source)
    monkeypatch.chdir(flat.parent)

    assert rules(Path("demo/cost.py")) == expected


def test_a_switch_waived_above_its_wrapped_statement_does_not_count_elsewhere(
    demo_package,
):
    tier = (
        "def tier(cfg):\n"
        "    return rate(\n"
        "        cfg,\n"
        "        'high' if cfg.backend == 'modal' else 'low',\n"
        "    )\n"
    )
    waiver = "    # conventions: ARC-9 - the price list alone knows every backend.\n"
    waived = tier.replace("    return", waiver + "    return", 1)
    demo = demo_package({"tier.py": tier, "start.py": START})

    before = rules(demo / "start.py")
    (demo / "tier.py").write_text(waived)

    assert (before, rules(demo / "start.py")) == ([(2, "ARC-9")], [])

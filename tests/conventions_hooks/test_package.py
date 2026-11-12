"""The checks that look past one file read the right modules of its package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conventions_hooks import package
from conventions_hooks.conventions import check_file, claude_hook

START = (
    "def start(cfg):\n"
    "    if cfg.backend == 'modal':\n        launch()\n"
    "    elif cfg.backend == 'local':\n        run()\n"
)
COST = "def cost(cfg):\n    if cfg.backend == 'modal':\n        return bill()\n"


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
def test_switches_across_modules_that_are_not_repeats_pass(demo_package, files):
    demo = demo_package(files)

    assert rules(demo / "a.py") == []


def test_a_module_outside_a_package_is_checked_alone(tmp_path):
    (tmp_path / "start.py").write_text(START)
    (tmp_path / "cost.py").write_text(COST)

    assert check_file(tmp_path / "start.py") == []


def test_tests_and_folders_that_are_not_packages_do_not_count(demo_package):
    demo = demo_package(
        {
            "cost.py": COST,
            "tests/test_start.py": START,
            "test_launch.py": START,
            "conftest.py": START,
        }
    )
    for stray in ("data/start.py", ".venv/lib/site/start.py"):
        (demo / stray).parent.mkdir(parents=True)
        (demo / stray).write_text(START)

    assert rules(demo / "cost.py") == []


def test_a_module_that_cannot_be_read_is_skipped(demo_package):
    demo = demo_package({"start.py": START, "cost.py": COST, "broken.py": "def (:\n"})
    (demo / ".#start.py").symlink_to("nobody@nowhere.1")
    (demo / "binary.py").write_bytes(b"\xff\xfe\x00")

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

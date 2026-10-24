"""The template's subagents give the labelled verdicts on seeded projects."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from copier import run_copy
from jinja2 import Template

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
LABELS = yaml.safe_load((HERE / "descriptions_labels.yaml").read_text())
VERDICTS = {"KEEP", "TRIM", "DROP", "ADD", "FIX", "RENAME", "UNSURE"}
# Planted by reviewer_report. A new module without tests, a CONTRIBUTING entry or an
# import layer also breaks TST-4, RDOC-5 and ARC-1, rightly.
PLANTED = {"ARC-4", "TYP-4", "LOG-2", "ERR-3", "DOC-7"}
CONSEQUENT = {"TST-4", "RDOC-5", "ARC-1"}
WORKER = '''"""Worker that processes queue items."""

from typing import Protocol

import structlog
from attrs import define

from nuikit.errors import DataError

log = structlog.stdlib.get_logger()


class Item(Protocol):
    """One queued item."""

    kind: str
    ok: bool

    def resize(self) -> None: ...


@define
class Worker:
    """Processor of the items in one queue."""

    name: str

    def __init__(self, name: str) -> None:
        self.name = name.strip()

    def handle(self, item: Item) -> None:
        """Process one item."""
        if not item.ok:
            raise DataError("Invalid item!")
        log.info("Started processing item")
        if item.kind == "image":
            item.resize()
'''

pytestmark = pytest.mark.judges


def sh(cwd: Path, *args: str) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def commit(project: Path, message: str) -> None:
    sh(project, "git", "add", "-A")
    sh(
        project,
        "git",
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        message,
    )


def ask_agent(project: Path, name: str, prompt: str) -> str:
    """Return the report of the project's subagent `name`, run as `claude -p` would."""
    result = subprocess.run(
        [
            "claude",
            "-p",
            "--agent",
            name,
            "--no-session-persistence",
            "--settings",
            '{"disableAllHooks": true}',
            "--allowedTools",
            "Read,Grep,Glob,Bash",
            "--disallowedTools",
            "Edit,Write,NotebookEdit",
        ],
        input=prompt,
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def table_rows(report: str) -> Iterator[list[str]]:
    for line in report.splitlines():
        if line.lstrip().startswith("|"):
            yield [
                c.strip().strip("`*").strip()
                for c in line.strip().strip("|").split("|")
            ]


@pytest.fixture(scope="module")
def descriptions_report(tmp_path_factory: pytest.TempPathFactory) -> str:
    project = tmp_path_factory.mktemp("descriptions")
    shutil.copytree(HERE / "fixtures" / "descriptions", project, dirs_exist_ok=True)
    agents = project / ".claude" / "agents"
    agents.mkdir(parents=True)
    source = (REPO / "shared" / "files" / "descriptions-judge.md.jinja").read_text()
    (agents / "descriptions-judge.md").write_text(
        Template(source).render(project_name="demo")
    )
    shutil.copy(REPO / "GUIDE.md", project / "CONVENTIONS.md")
    sh(project, "git", "init", "-q", "-b", "main")
    commit(project, "init")
    return ask_agent(project, "descriptions-judge", "Scope: the whole repository.")


@pytest.mark.parametrize("label", LABELS, ids=lambda x: f"{x['path']}:{x['setting']}")
def test_the_descriptions_judge_gives_the_labelled_verdict(label, descriptions_report):
    found = {
        row[0].upper()
        for row in table_rows(descriptions_report)
        if len(row) >= 3
        and row[0].upper() in VERDICTS
        and label["path"] in row[1]
        and re.search(rf"\b{label['setting']}\b", row[2])
    }
    expect = set(label["expect"])

    if "KEEP" in expect:
        assert not found & ({"DROP", "TRIM", "FIX"} - expect), descriptions_report
    elif expect == {"NONE"}:
        assert not found & {"ADD", "RENAME"}, descriptions_report
    else:
        assert found & expect, descriptions_report


@pytest.fixture(scope="module")
def reviewer_report(tmp_path_factory: pytest.TempPathFactory) -> str:
    # A plain copy: copier renders a git template from its last commit.
    template = tmp_path_factory.mktemp("template")
    ignore = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache")
    shutil.copytree(REPO, template, ignore=ignore, dirs_exist_ok=True)
    project = tmp_path_factory.mktemp("reviewed") / "demo"
    run_copy(
        str(template),
        project,
        data={"profile": "rnd", "project_name": "demo"},
        defaults=True,
        quiet=True,
    )
    sh(project, "git", "init", "-q", "-b", "main")
    commit(project, "init")
    sh(project, "git", "switch", "-qc", "feat/worker")
    (project / "src" / "demo" / "worker.py").write_text(WORKER)
    with (project / "configs" / "run.yaml").open("a") as f:
        f.write("\nseed: 7  # The seed.\n")
    commit(project, "feat: add queue worker")
    return ask_agent(project, "conventions-reviewer", "Review this branch.")


def flagged(report: str) -> set[str]:
    """Return the rule IDs the report marks VIOLATES or PARTIAL, expanding ARC-2/4."""
    rules: set[str] = set()
    for row in table_rows(report):
        if len(row) >= 2 and row[1].upper().startswith(("VIOLATES", "PARTIAL")):
            for prefix, numbers in re.findall(r"([A-Z]+)-(\d+(?:/\d+)*)", row[0]):
                rules |= {f"{prefix}-{n}" for n in numbers.split("/")}
    return rules


@pytest.mark.parametrize("rule", sorted(PLANTED))
def test_the_conventions_reviewer_flags_each_planted_violation(rule, reviewer_report):
    assert rule in flagged(reviewer_report), reviewer_report


def test_the_conventions_reviewer_flags_nothing_that_was_not_planted(reviewer_report):
    assert flagged(reviewer_report) <= PLANTED | CONSEQUENT, reviewer_report

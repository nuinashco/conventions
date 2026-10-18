"""Every profile renders into a project whose own checks pass."""

import shutil
import subprocess
from pathlib import Path

import pytest
from copier import run_copy

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # A plain copy: copier renders a git template from its last commit, and this
    # suite must test the working tree.
    src = tmp_path_factory.mktemp("template")
    ignore = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache")
    shutil.copytree(REPO, src, ignore=ignore, dirs_exist_ok=True)
    return src


def render(template: Path, dst: Path, **data: object) -> Path:
    run_copy(str(template), dst, data=data, defaults=True, quiet=True)
    sh(dst, "git", "init", "-q")
    return dst


def sh(cwd: Path, *args: str) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"{' '.join(args)}\n{result.stdout}\n{result.stderr}"
    return result.stdout


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"python": "3.12", "use_wandb": True},
    ],
    ids=["latest-python", "py312-wandb"],
)
def test_rnd_project_passes_its_checks_and_runs(template, tmp_path, data):
    project = render(
        template, tmp_path / "demo", profile="rnd", project_name="demo", **data
    )

    sh(project, "make", "check")
    sh(project, "uv", "run", "demo-run", "run_name=smoke")
    sh(project, "uv", "run", "demo-configs", "--check")

    assert (project / "runs" / "smoke" / "run.json").is_file()


def test_uni_workspace_with_two_labs_passes_its_checks(template, tmp_path):
    course = render(template, tmp_path / "course", profile="uni", project_name="course")

    sh(course, "make", "lab", "N=001", "TOPIC=first")
    sh(course, "make", "lab", "N=002", "TOPIC=second")
    sh(course, "make", "check")
    sh(course, "uv", "run", "course", "configs", "--check")

    assert (course / "labs" / "002-second" / "src" / "lab002" / "config.py").is_file()

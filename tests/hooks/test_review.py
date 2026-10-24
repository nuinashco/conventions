"""The comment review asks Claude only when needed and reads its verdict."""

from __future__ import annotations

import json
import subprocess

import pytest

from conventions_hooks.review import (
    FALLBACK_RULES,
    ReviewError,
    claude_hook,
    command,
    review,
    rules,
)

FINDING = {
    "path": "new.py",
    "line": 1,
    "quote": "# Add one.",
    "rule": "DOC-4",
    "problem": "restates the code",
    "fix": "delete it",
}


def verdict(*findings: dict[str, object]) -> str:
    """Return `claude -p --output-format json` output carrying `findings`."""
    output = {"findings": list(findings), "verdict": "FAIL" if findings else "PASS"}
    return json.dumps({"is_error": False, "structured_output": output})


def answering(text: str, calls: list[str]):
    def ask(args: list[str], stdin: str) -> str:
        calls.append(stdin)
        return text

    return ask


def test_an_empty_diff_passes_without_asking():
    calls: list[str] = []

    assert review("", "rules", ask=answering(verdict(FINDING), calls)) == (True, "")
    assert calls == []


def test_findings_come_back_as_lines_with_their_quote_and_fix():
    calls: list[str] = []

    passed, text = review(
        "+# Add one.", "rules", ask=answering(verdict(FINDING), calls)
    )

    assert not passed
    assert text == "FAIL\nnew.py:1: DOC-4 restates the code ('# Add one.'); delete it"
    assert "+# Add one." in calls[0]


def test_an_answer_without_a_structured_verdict_is_an_error():
    with pytest.raises(ReviewError, match="no verdict"):
        review("+# Add one.", "rules", ask=answering('{"result": "FAIL"}', []))


def test_the_review_runs_with_hooks_off_so_it_cannot_trigger_itself():
    args = command()

    settings = json.loads(args[args.index("--settings") + 1])
    assert settings == {"disableAllHooks": True}


def test_rules_come_from_the_guide_section_or_the_fallback(tmp_path):
    assert rules(tmp_path) == FALLBACK_RULES
    guide = "## 7. Code\n\n## 8. Comments and docstrings\n\nRule.\n\n## 9. Errors\n"
    (tmp_path / "CONVENTIONS.md").write_text(guide)

    assert rules(tmp_path) == "## 8. Comments and docstrings\n\nRule."


@pytest.fixture
def repo(tmp_path):
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "module.py").write_text("x = 1\n")
    git("add", "-A")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return tmp_path


def stop(*, active: bool = False) -> str:
    return json.dumps({"stop_hook_active": active})


def test_the_stop_hook_skips_turns_without_new_comments(repo):
    calls: list[str] = []
    (repo / "module.py").write_text("x = 2\n")

    assert claude_hook(stop(), repo, ask=answering(verdict(FINDING), calls)) == 0
    assert calls == []


def test_the_stop_hook_hands_findings_to_claude_once_per_turn(repo, capsys):
    calls: list[str] = []
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    ask = answering(verdict(FINDING), calls)

    assert claude_hook(stop(active=True), repo, ask=ask) == 0
    assert claude_hook(stop(), repo, ask=ask) == 2
    assert "+# Add one." in calls[0]
    assert "DOC-4" in capsys.readouterr().err


def test_the_stop_hook_does_not_review_a_passed_diff_again(repo):
    calls: list[str] = []
    (repo / "module.py").write_text("x = 2  # Seconds, as the scorer counts them.\n")

    assert claude_hook(stop(), repo, ask=answering(verdict(), calls)) == 0
    assert claude_hook(stop(), repo, ask=answering(verdict(), calls)) == 0
    assert len(calls) == 1

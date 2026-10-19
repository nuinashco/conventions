"""The comment review asks Claude only when needed and reads its verdict."""

from __future__ import annotations

import json
import subprocess

import pytest

from conventions_hooks.review import FALLBACK_RULES, claude_hook, review, rules


def answering(text: str, calls: list[str]):
    def ask(args: list[str], stdin: str) -> str:
        calls.append(stdin)
        return text

    return ask


def test_an_empty_diff_passes_without_asking():
    calls: list[str] = []

    assert review("", "rules", ask=answering("FAIL", calls)) == (True, "")
    assert calls == []


def test_the_verdict_comes_from_the_first_line():
    calls: list[str] = []
    answer = "FAIL\nmod.py:3: DOC-4 restates the code; delete it"

    passed, text = review("+# Add one.", "rules", ask=answering(answer, calls))

    assert (passed, text) == (False, answer)
    assert "+# Add one." in calls[0]


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

    assert claude_hook(stop(), repo, ask=answering("FAIL", calls)) == 0
    assert calls == []


def test_the_stop_hook_hands_findings_to_claude_once_per_turn(repo, capsys):
    calls: list[str] = []
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    ask = answering("FAIL\nnew.py:1: DOC-4 restates the code; delete it", calls)

    assert claude_hook(stop(active=True), repo, ask=ask) == 0
    assert claude_hook(stop(), repo, ask=ask) == 2
    assert "+# Add one." in calls[0]
    assert "DOC-4" in capsys.readouterr().err


def test_the_stop_hook_does_not_review_a_passed_diff_again(repo):
    calls: list[str] = []
    (repo / "module.py").write_text("x = 2  # Seconds, as the scorer counts them.\n")

    assert claude_hook(stop(), repo, ask=answering("PASS", calls)) == 0
    assert claude_hook(stop(), repo, ask=answering("PASS", calls)) == 0
    assert len(calls) == 1

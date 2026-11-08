"""The comment review asks Claude only when needed and reads its verdict."""

from __future__ import annotations

import json
import subprocess

import pytest

from conventions_hooks.review import (
    ReviewError,
    claude_hook,
    command,
    comment_rules,
    review,
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


def test_findings_under_an_ignored_rule_are_dropped_and_then_pass():
    calls: list[str] = []
    ask = answering(verdict(FINDING), calls)

    assert review("+# Add one.", "rules", ask=ask, ignore=frozenset({"DOC-4"})) == (
        True,
        "PASS",
    )


def test_a_repo_that_ignores_every_judged_rule_is_not_reviewed():
    calls: list[str] = []
    ignore = frozenset(f"DOC-{n}" for n in range(1, 8))

    passed = review(
        "+# Add one.", "rules", ask=answering(verdict(), calls), ignore=ignore
    )

    assert (passed, calls) == ((True, ""), [])


def test_an_answer_without_a_structured_verdict_is_an_error():
    with pytest.raises(ReviewError, match="no verdict"):
        review("+# Add one.", "rules", ask=answering('{"result": "FAIL"}', []))


def test_the_review_runs_with_hooks_off_so_it_cannot_trigger_itself():
    args = command()

    settings = json.loads(args[args.index("--settings") + 1])
    assert settings == {"disableAllHooks": True}


def test_the_judge_gets_the_comment_rules_shipped_with_the_package():
    rules = comment_rules()

    assert rules.startswith("# Comments and docstrings (DOC)")
    assert "### DOC-4 MUST" in rules
    assert "### DOC-7 MUST" in rules


@pytest.fixture
def repo(opted_in):
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=opted_in, check=True, capture_output=True)

    git("init", "-q")
    (opted_in / "module.py").write_text("x = 1\n")
    git("add", "-A")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return opted_in


def stop(*, active: bool = False) -> str:
    return json.dumps({"stop_hook_active": active})


def test_the_stop_hook_skips_a_repo_that_has_not_opted_in(repo, capsys):
    calls: list[str] = []
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")

    assert claude_hook(stop(), repo, ask=answering(verdict(FINDING), calls)) == 0
    assert (calls, capsys.readouterr().err) == ([], "")


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


def test_the_stop_hook_hands_the_same_findings_to_claude_only_once(repo):
    calls: list[str] = []
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    ask = answering(verdict(FINDING), calls)

    assert (claude_hook(stop(), repo, ask=ask), claude_hook(stop(), repo, ask=ask)) == (
        2,
        0,
    )
    assert len(calls) == 1


def test_the_stop_hook_does_not_review_a_passed_diff_again(repo):
    calls: list[str] = []
    (repo / "module.py").write_text("x = 2  # Seconds, as the scorer counts them.\n")

    assert claude_hook(stop(), repo, ask=answering(verdict(), calls)) == 0
    assert claude_hook(stop(), repo, ask=answering(verdict(), calls)) == 0
    assert len(calls) == 1

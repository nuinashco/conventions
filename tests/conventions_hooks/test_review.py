"""The comment review asks Claude only when needed and reads its verdict."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from conventions_hooks.review import (
    JUDGED,
    ReviewError,
    ask_claude,
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


def sent(stdin: str) -> str:
    """Return the diff in what the judge was sent, without the rules before it."""
    return stdin.partition("# Diff\n\n")[2]


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


def test_a_diff_over_200000_characters_is_an_error_and_is_not_sent():
    calls: list[str] = []
    ask = answering(verdict(), calls)
    at_limit = "+#" + "x" * 199_998

    assert review(at_limit, "rules", ask=ask) == (True, "PASS")
    with pytest.raises(
        ReviewError,
        match="span 200001 characters of diff, over the limit of 200000; not reviewed",
    ):
        review(at_limit + "x", "rules", ask=ask)
    assert len(calls) == 1


def test_the_review_runs_with_hooks_tools_and_mcp_servers_off():
    args = command()

    settings = json.loads(args[args.index("--settings") + 1])
    assert settings == {"disableAllHooks": True}
    assert (args[args.index("--tools") + 1], "--strict-mcp-config" in args) == (
        "",
        True,
    )
    assert "--mcp-config" not in args


def test_the_judge_gets_the_comment_rules_shipped_with_the_package():
    rules = comment_rules()

    assert rules.startswith("# Comments and docstrings (DOC)")
    assert "### DOC-4 MUST" in rules
    assert "### DOC-7 MUST" in rules


def test_a_judge_that_gives_no_answer_in_time_is_an_error_saying_how_long(
    tmp_path, monkeypatch
):
    (tmp_path / "claude").write_text("#!/bin/sh\nexec sleep 5\n")
    (tmp_path / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)

    with pytest.raises(ReviewError, match=r"claude gave no answer in 0\.2 seconds"):
        ask_claude(["claude", "-p"], "diff", timeout_s=0.2)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def commit(repo: Path) -> None:
    identity = ("-c", "user.email=t@t", "-c", "user.name=t")
    git(repo, "add", "-A")
    # A developer who signs commits has no key for this identity.
    git(repo, *identity, "-c", "commit.gpgsign=false", "commit", "-qm", "init")


@pytest.fixture
def repo(opted_in):
    git(opted_in, "init", "-q")
    (opted_in / "module.py").write_text("x = 1\n")
    commit(opted_in)
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


def test_a_finding_left_in_place_is_not_reviewed_again_after_a_code_only_edit(repo):
    calls: list[str] = []
    ask = answering(verdict(FINDING), calls)
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    first = claude_hook(stop(), repo, ask=ask)
    (repo / "module.py").write_text("x = 2\n")

    second = claude_hook(stop(), repo, ask=ask)

    assert (first, second, len(calls)) == (2, 0, 1)


def test_a_new_comment_elsewhere_is_sent_alone_and_the_old_finding_is_not_repeated(
    repo, capsys
):
    calls: list[str] = []
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    claude_hook(stop(), repo, ask=answering(verdict(FINDING), calls))
    capsys.readouterr()
    (repo / "other.py").write_text("# Add two.\ny = 1 + 2\n")
    other = {**FINDING, "path": "other.py", "quote": "# Add two."}

    code = claude_hook(stop(), repo, ask=answering(verdict(FINDING, other), calls))

    assert (code, len(calls)) == (2, 2)
    assert ("new.py" in sent(calls[1]), "+++ b/other.py" in sent(calls[1])) == (
        False,
        True,
    )
    assert capsys.readouterr().err == (
        "FAIL\nother.py:1: DOC-4 restates the code ('# Add two.'); delete it\n"
    )


def test_a_finding_is_not_repeated_when_its_hunk_is_sent_again(repo, capsys):
    calls: list[str] = []
    ask = answering(verdict(FINDING), calls)
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    first = claude_hook(stop(), repo, ask=ask)
    capsys.readouterr()
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\nwait = 5  # Seconds.\n")

    second = claude_hook(stop(), repo, ask=ask)

    assert (first, second, len(calls), capsys.readouterr().err) == (2, 0, 2, "")


def test_only_the_hunk_with_a_new_comment_is_sent_under_its_file_header(repo):
    calls: list[str] = []
    ask = answering(verdict(), calls)
    body = [f"v{n} = {n}" for n in range(20)]
    (repo / "module.py").write_text("\n".join(body) + "\n")
    commit(repo)
    (repo / "module.py").write_text("\n".join(["# First.", *body]) + "\n")
    claude_hook(stop(), repo, ask=ask)
    (repo / "module.py").write_text("\n".join(["# First.", *body, "# Last."]) + "\n")

    claude_hook(stop(), repo, ask=ask)

    header, hunk = sent(calls[1]).split("\n@@ ")
    assert header.endswith("\n--- a/module.py\n+++ b/module.py")
    assert hunk.startswith("-18,3 +19,4 @@")
    assert hunk.endswith("\n v17 = 17\n v18 = 18\n v19 = 19\n+# Last.")


def test_a_comment_removed_and_written_again_is_sent_again(repo):
    calls: list[str] = []
    ask = answering(verdict(), calls)
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    claude_hook(stop(), repo, ask=ask)
    (repo / "new.py").write_text("x = 1 + 1\n")
    claude_hook(stop(), repo, ask=ask)
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")

    claude_hook(stop(), repo, ask=ask)

    assert ["+# Add one." in sent(call) for call in calls] == [True, True]


def test_a_finding_is_forgotten_once_its_file_has_left_the_diff(repo):
    calls: list[str] = []
    ask = answering(verdict(FINDING), calls)
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    claude_hook(stop(), repo, ask=ask)
    commit(repo)
    claude_hook(stop(), repo, ask=ask)
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n# Add one.\ny = 1 + 1\n")

    assert (claude_hook(stop(), repo, ask=ask), len(calls)) == (2, 2)


def test_a_reviewed_comment_that_is_only_indented_is_not_sent_again(repo):
    calls: list[str] = []
    ask = answering(verdict(), calls)
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    claude_hook(stop(), repo, ask=ask)
    (repo / "new.py").write_text("if True:\n    # Add one.\n    x = 1 + 1\n")

    claude_hook(stop(), repo, ask=ask)

    assert len(calls) == 1


def test_a_file_moved_with_git_is_not_new_text(repo):
    calls: list[str] = []
    (repo / "old.py").write_text("# Add one.\nx = 1 + 1\n")
    commit(repo)
    git(repo, "mv", "old.py", "moved.py")

    code = claude_hook(stop(), repo, ask=answering(verdict(FINDING), calls))

    assert (code, calls) == (0, [])


def test_an_untracked_file_named_with_a_space_and_a_non_ascii_letter_is_reviewed(
    repo,
):
    calls: list[str] = []
    (repo / "my caf\u00e9.py").write_text("# Add one.\nx = 1 + 1\n")

    claude_hook(stop(), repo, ask=answering(verdict(), calls))

    assert "+++ b/my caf\u00e9.py" in sent(calls[0])
    assert "+# Add one." in sent(calls[0])


def test_a_file_that_is_not_utf8_is_reviewed_with_its_odd_bytes_replaced(repo):
    calls: list[str] = []
    (repo / "latin.py").write_bytes(b"# Caf\xe9 hours.\nx = 1\n")

    code = claude_hook(stop(), repo, ask=answering(verdict(), calls))

    assert (code, "+# Caf\ufffd hours." in sent(calls[0])) == (0, True)


@pytest.mark.parametrize(
    "pyproject",
    [
        '[project]\nname = "member"\n',
        f"[tool.conventions]\nignore = {json.dumps(sorted(JUDGED))}\n",
        "[tool.conventions\n",
    ],
    ids=["no-table", "every-judged-rule-ignored", "table-does-not-parse"],
)
def test_a_member_is_left_out_unless_its_own_table_asks_for_the_review(repo, pyproject):
    calls: list[str] = []
    (repo / "member").mkdir()
    (repo / "member" / "pyproject.toml").write_text(pyproject)
    (repo / "member" / "mod.py").write_text("# Add one.\nx = 1 + 1\n")
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")

    claude_hook(stop(), repo, ask=answering(verdict(), calls))

    assert ("+++ b/new.py" in sent(calls[0]), "member/mod.py" in sent(calls[0])) == (
        True,
        False,
    )


def test_a_member_with_its_own_table_is_reviewed_in_a_repo_without_one(repo):
    calls: list[str] = []
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (repo / "member").mkdir()
    (repo / "member" / "pyproject.toml").write_text("[tool.conventions]\n")
    (repo / "member" / "mod.py").write_text("# Add one.\nx = 1 + 1\n")
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")

    claude_hook(stop(), repo, ask=answering(verdict(), calls))

    assert ("+++ b/new.py" in sent(calls[0]), "member/mod.py" in sent(calls[0])) == (
        False,
        True,
    )


def test_a_finding_is_dropped_when_the_table_of_its_file_ignores_the_rule(repo, capsys):
    calls: list[str] = []
    (repo / "member").mkdir()
    (repo / "member" / "pyproject.toml").write_text(
        '[tool.conventions]\nignore = ["DOC-4"]\n'
    )
    (repo / "member" / "mod.py").write_text("# Add one.\nx = 1 + 1\n")
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    answer = verdict(FINDING, {**FINDING, "path": "member/mod.py"})

    code = claude_hook(stop(), repo, ask=answering(answer, calls))

    assert (code, capsys.readouterr().err) == (
        2,
        "FAIL\nnew.py:1: DOC-4 restates the code ('# Add one.'); delete it\n",
    )


def test_a_state_file_in_the_old_format_counts_as_empty(repo):
    calls: list[str] = []
    ask = answering(verdict(), calls)
    (repo / ".git" / "review-comments").write_text("6c1a2bb5" * 8)
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")

    codes = (claude_hook(stop(), repo, ask=ask), claude_hook(stop(), repo, ask=ask))

    assert (codes, len(calls)) == ((0, 0), 1)


def test_the_stop_hook_skips_a_diff_over_the_limit_with_one_line(repo, capsys):
    calls: list[str] = []
    ask = answering(verdict(), calls)
    state = repo / ".git" / "review-comments"
    (repo / "new.py").write_text("# Add one.\nx = 1 + 1\n")
    claude_hook(stop(), repo, ask=ask)
    before = state.read_text()
    (repo / "table.py").write_text("# Generated table.\n" + "x = 1\n" * 40_000)

    code = claude_hook(stop(), repo, ask=ask)

    assert (code, len(calls), state.read_text()) == (1, 1, before)
    assert re.fullmatch(
        r"review-comments: the new comments span \d+ characters of diff, over the "
        r"limit of 200000; not reviewed\n",
        capsys.readouterr().err,
    )

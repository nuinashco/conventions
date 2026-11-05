"""The generator reads rules/ in its one shape and writes every file derived from it."""

from __future__ import annotations

from pathlib import Path

import pytest

from conventions_hooks.rules import (
    Area,
    Guide,
    Rule,
    RulesError,
    agent_page,
    main,
    skill_page,
)

INTRO = """\
---
title: Demo guide
areas: [ABC, DOC]
retired: [ABC-9]
---

Rules for demos.

## How to read

Carefully.
"""
ABC = """\
---
area: ABC
title: Alphabet
skill: alphabet
description: Use when spelling.
paths: ["**/*.py"]
---

### ABC-1 MUST

Letters come in order. Nothing else.

*Why:* readers expect it.

*Check:* review.

### ABC-2 SHOULD [rnd]

Vowels are optional, e.g. in names.

*Check:* `check-abc`; review for the rest.
"""
DOC = """\
---
area: DOC
title: Comments and docstrings
skill: comments
description: Use when commenting.
---

### DOC-1 MUST

Every module has a docstring.

*Check:* ruff D100.
"""
REVIEWER = (
    "---\nname: reviewer\n---\n\nJudge these:\n\n{{checklist}}\n\n{{ rule:DOC-1 }}\n"
)


def rule(*, body: str = "Body.", check: str = "review.") -> Rule:
    return Rule(id="ABC-1", level="MUST", tag="", body=body, why="", check=check)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "_intro.md").write_text(INTRO)
    (rules / "abc.md").write_text(ABC)
    (rules / "doc.md").write_text(DOC)
    (rules / "_decisions.md").write_text("---\ntitle: Decisions\n---\n\n| a | b |\n")
    (rules / "_sources.md").write_text("---\ntitle: Sources\n---\n\n- a book\n")
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "conventions-reviewer.md").write_text(REVIEWER)
    (tmp_path / "agents" / "descriptions-judge.md").write_text(
        "---\nname: judge\n---\n\nJudge.\n"
    )
    return tmp_path


@pytest.mark.parametrize(
    ("check", "review_only"),
    [
        ("review.", True),
        ("review (grep `kind ==`); review for the names.", True),
        ("ruff N; review.", False),
        ("`review-comments` asks Claude.", False),
    ],
    ids=["review", "two-reviews", "tool-and-review", "tool-named-review"],
)
def test_a_rule_is_review_only_when_every_part_of_its_check_is_review(
    check, review_only
):
    assert rule(check=check).review_only is review_only


@pytest.mark.parametrize(
    ("body", "summary"),
    [
        (
            "Short one. It takes the next sentence along with it. Not this.",
            "Short one. It takes the next sentence along with it.",
        ),
        (
            "A sentence of ten words or more stands on its own here. Not this.",
            "A sentence of ten words or more stands on its own here.",
        ),
        (
            "Use `x.y` and [a link. Here](u) or e.g. this; it ends here. No.",
            "Use `x.y` and [a link. Here](u) or e.g. this; it ends here.",
        ),
        (
            "A lead-in ending with a colon:\n\n- a list",
            "A lead-in ending with a colon.",
        ),
    ],
    ids=["short", "long", "code-link-abbreviation", "colon"],
)
def test_the_summary_is_the_opening_sentence_or_two(body, summary):
    assert rule(body=body).summary == summary


def test_the_guide_keeps_areas_in_the_order_the_intro_gives(repo):
    guide = Guide.load(repo / "rules")

    assert [area.code for area in guide.areas] == ["ABC", "DOC"]
    assert [r.label for r in guide.area("ABC").rules] == ["MUST", "SHOULD [rnd]"]
    assert guide.rule("ABC-1").why == "readers expect it."


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        (
            ABC.replace("\n\n*Check:* review.", ""),
            "must end with one `\\*Check:\\* ...`",
        ),
        (
            ABC.replace("*Why:* readers expect it.\n\n", "") + "\n*Why:* late.\n",
            "must end",
        ),
        (ABC.replace("### ABC-2", "### XYZ-2"), "do not belong to ABC"),
        (ABC.replace("skill: alphabet", "skill: Alphabet"), "not kebab-case"),
        (
            ABC.replace("### ABC-2 SHOULD [rnd]", "### ABC-9 SHOULD"),
            "retired rule IDs reused",
        ),
        (ABC.replace("### ABC-2", "### ABC-1"), "used twice"),
    ],
    ids=[
        "no-check",
        "why-after-check",
        "foreign-id",
        "skill-name",
        "retired-id",
        "repeated-id",
    ],
)
def test_a_rule_file_out_of_shape_is_an_error_naming_it(repo, text, problem):
    (repo / "rules" / "abc.md").write_text(text)

    with pytest.raises(RulesError, match=problem):
        Guide.load(repo / "rules")


def test_a_skill_has_review_only_rules_in_full_and_the_rest_in_brief(repo):
    area: Area = Guide.load(repo / "rules").area("ABC")

    page = skill_page(area)

    frontmatter = (
        "name: alphabet\ndescription: Use when spelling.\npaths:\n- '**/*.py'\n"
    )
    assert page.startswith(f"---\n{frontmatter}---\n")
    assert "### ABC-1 MUST\n\nLetters come in order. Nothing else.\n\n*Why:*" in page
    assert (
        "- **ABC-2** SHOULD [rnd]: Vowels are optional, e.g. in names. "
        "*Check:* `check-abc`; review for the rest."
    ) in page


def test_an_agent_gets_the_checklist_and_any_rule_it_quotes(repo):
    guide = Guide.load(repo / "rules")

    page = agent_page(REVIEWER, guide, source="agents/conventions-reviewer.md")

    assert "  - **ABC-1** MUST: Letters come in order. Nothing else." in page
    assert "- **ABC-2** SHOULD [rnd]: Vowels are optional" in page
    assert "### DOC-1 MUST\n\nEvery module has a docstring." in page
    with pytest.raises(RulesError, match="unknown placeholder 'name'"):
        agent_page("---\nname: x\n---\n{{name}}\n", guide, source="agents/x.md")


def test_check_names_stale_files_and_a_build_brings_them_up_to_date(
    repo, monkeypatch, capsys
):
    monkeypatch.chdir(repo)
    orphan = repo / "plugins" / "conventions" / "skills" / "gone" / "SKILL.md"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("old\n")

    assert main(["--check"]) == 1
    assert "plugins/conventions/skills/gone/SKILL.md: stale" in capsys.readouterr().out
    assert main([]) == 0
    assert main(["--check"]) == 0
    assert not orphan.parent.exists()
    assert (repo / "GUIDE.md").read_text().startswith("<!-- Generated by `make build`")
    assert (repo / "src" / "conventions_hooks" / "doc_rules.md").is_file()


def test_a_missing_rules_directory_is_reported_without_a_traceback(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)

    assert main(["--check"]) == 2
    assert "run build-rules at the repo root" in capsys.readouterr().err

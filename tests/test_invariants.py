"""Repo-wide invariants: generated files are fresh, the plugin wires real commands."""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from pathlib import Path

from conventions_hooks import rules

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "conventions"
RUN_CHECK = '"${CLAUDE_PLUGIN_ROOT}/bin/run-check"'


def test_generated_files_are_fresh():
    assert rules.stale(REPO) == [], "run `make build`"


def test_plugin_hooks_run_console_scripts_of_this_package_on_their_events():
    scripts = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"]
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]

    wired = {
        (event, group.get("matcher", ""), shlex.split(hook["command"])[1])
        for event, groups in hooks.items()
        for group in groups
        for hook in group["hooks"]
        if hook["command"].startswith(f"{RUN_CHECK} ")
        and hook["command"].endswith(" --claude-hook")
    }

    assert wired == {
        ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit", "check-protected"),
        ("PostToolUse", "Edit|Write|MultiEdit", "check-comments"),
        ("PostToolUse", "Edit|Write|MultiEdit", "check-conventions"),
        ("Stop", "", "review-comments"),
    }
    assert {command for *_, command in wired} <= set(scripts)


def test_marketplace_lists_both_plugins_with_sources_that_resolve():
    marketplace = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    plugins = {plugin["name"]: plugin["source"] for plugin in marketplace["plugins"]}
    local = json.loads(
        (REPO / plugins["conventions"] / ".claude-plugin" / "plugin.json").read_text()
    )

    assert (marketplace["name"], marketplace["owner"]) == (
        "nuinashco",
        {"name": "nuinashco"},
    )
    assert set(plugins) == {"conventions", "nuikit"}
    assert plugins["conventions"] == "./plugins/conventions"
    assert (local["name"], "version" in local) == ("conventions", False)
    assert plugins["nuikit"] == {
        "source": "git-subdir",
        "url": "https://github.com/nuinashco/nuikit.git",
        "path": "plugin",
    }


def test_every_skill_and_agent_starts_with_frontmatter_naming_it():
    pages = [*PLUGIN.glob("skills/*/SKILL.md"), *PLUGIN.glob("agents/*.md")]
    names = {page: re.match(r"---\nname: (\S+)\n", page.read_text()) for page in pages}

    assert pages
    assert all(names.values()), [str(page) for page, name in names.items() if not name]
    assert all(
        name[1] == page.parent.name
        for page, name in names.items()
        if name and page.name == "SKILL.md"
    )

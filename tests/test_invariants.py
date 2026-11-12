"""Repo-wide invariants: generated files are fresh, the plugin wires real commands."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from conventions_hooks import rules

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "conventions"
RUN_CHECK = '"${CLAUDE_PLUGIN_ROOT}/scripts/run-check"'
HOOK = re.compile(rf"{re.escape(RUN_CHECK)} (\S+) --claude-hook")
BASH_BLOCK = re.compile(r"^ *```bash\n(.*?)^ *```$", re.M | re.S)


def test_generated_files_are_fresh():
    assert rules.stale(REPO) == [], "run `make build`"


def hook_script(command: str) -> str:
    """Return the console script that a plugin hook's `command` runs."""
    match = HOOK.fullmatch(command)
    assert match, f"{command!r} is not `{RUN_CHECK} <script> --claude-hook`"
    return match[1]


def test_plugin_hooks_run_console_scripts_of_this_package_on_their_events():
    scripts = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"]
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]

    wired = sorted(
        (event, group.get("matcher", ""), hook_script(hook["command"]))
        for event, groups in hooks.items()
        for group in groups
        for hook in group["hooks"]
    )

    assert wired == [
        ("PostToolUse", "Edit|Write|MultiEdit", "check-comments"),
        ("PostToolUse", "Edit|Write|MultiEdit", "check-conventions"),
        ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit", "check-protected"),
        ("Stop", "", "review-comments"),
    ]
    assert {script for *_, script in wired} <= set(scripts)


def test_only_the_stop_hook_runs_in_the_background():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]

    background = {
        (event, hook_script(hook["command"])): hook.get("asyncRewake", False)
        for event, groups in hooks.items()
        for group in groups
        for hook in group["hooks"]
    }

    assert {key for key, rewakes in background.items() if rewakes} == {
        ("Stop", "review-comments")
    }
    assert not any(
        hook.get("async")
        for groups in hooks.values()
        for g in groups
        for hook in g["hooks"]
    )


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


def test_command_blocks_of_the_documents_hold_only_commands():
    # An interactive zsh hands a trailing `# comment` to the command as arguments.
    commented = [
        f"{name}: {line.strip()}"
        for name in ("README.md", "CONTRIBUTING.md")
        for block in BASH_BLOCK.findall((REPO / name).read_text())
        for line in block.splitlines()
        if "#" in line
    ]

    assert commented == []

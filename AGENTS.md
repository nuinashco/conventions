# AGENTS.md

This repo holds the nuinashco conventions: the rules as data in `rules/`, the `conventions-hooks` package that checks
them, and the `conventions` Claude Code plugin with the `nuinashco` marketplace. Users: [README.md](README.md).
Layout and deviations: [CONTRIBUTING.md](CONTRIBUTING.md). The repo follows its own rules (GUIDE.md).

## Commands

```bash
make setup        # uv sync + git hooks
make check        # ruff, pyright, pytest, generated files fresh: must pass before every commit
make build        # regenerate GUIDE.md, COVERAGE.md, plugins/conventions/{skills,agents}, doc_rules.md
make test-judges  # live `claude` runs of the judges on tests/judges/ (costs tokens)
```

## Working here

- Rules live in `rules/<area>.md`. Edit them there, never in GUIDE.md, COVERAGE.md, the plugin's `skills/` or
  `agents/`, or `src/conventions_hooks/doc_rules.md`: `make build` writes those, and a test fails while they are
  stale. Subagent prompts are written in `agents/*.md`; `{{checklist}}` and `{{rule:ID}}` are filled in by the build.
- A rule keeps its shape: `### <ID> <LEVEL>`, the body, an optional `*Why:*` paragraph, a final `*Check:*` paragraph.
  Keep the ID; never reuse a retired one (`retired` in `rules/_intro.md`). Rule IDs that moved to nuinashco/nuikit or
  nuinashco/rnd-template are changed there.
- Prefer a check a tool can run: a new mechanical check goes into `check-conventions` (or a new hook) with tests,
  and the rule's *Check* names it.
- A hook's `--claude-hook` mode exits 0 silently in a repo without `[tool.conventions]`; every mode honours its
  `ignore`. The plugin's `scripts/run-check` relies on that silence: it never looks for the table. Keep the console
  script names: `plugins/conventions/hooks/hooks.json` and projects' pre-commit configs call them.
- A change to a judge's prompt (`agents/`, `review.py`) or model is measured with `make test-judges` before
  committing; a mistake a judge makes becomes a case in `tests/judges/` (TOOL-6).
- Releases are tags (`vMAJOR.MINOR.PATCH`) that projects pin; the plugin follows the default branch.
- Commits: one line, Conventional Commits, lowercase imperative subject, no articles (GIT-1, GIT-2).

## Layout

```text
rules/                    the rules: one file per area, plus _intro, _decisions, _sources
agents/                   sources of the plugin's subagents
src/conventions_hooks/    the hooks, settings.py ([tool.conventions]), rules.py (build-rules)
plugins/conventions/      the plugin: .claude-plugin/plugin.json, hooks/, scripts/run-check, generated skills/ and agents/
.claude-plugin/           marketplace.json of the nuinashco marketplace
tests/                    conventions_hooks/: unit tests; test_invariants.py, test_run_check.py; judges/: cases
```

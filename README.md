# conventions

My conventions for Python and ML projects, and the copier templates that implement them.

- [GUIDE.md](GUIDE.md): the rules (MUST/SHOULD/MAY, each with a reason and a check), the decisions behind them, and
  sources.
- `templates/rnd`: research and development projects. These are tools, pipelines and training code, built as one
  package with Hydra + pydantic configs, families of items, run directories, structlog, attrs, pyright and
  import-linter.
- `templates/uni`: course workspaces. A uv workspace with a shared course package, one member per lab, and LaTeX
  reports built from generated macros.
- `templates/lab`: one lab inside a uni workspace, created with `make lab` there.

## Hooks

The repo is also the `conventions-hooks` package (`src/conventions_hooks/`), the checks this guide adds on top of ruff:

| command | checks | runs |
|---|---|---|
| `check-comments` | comments are sentences, no section banners, class docstrings are noun phrases (DOC-2, DOC-4, DOC-5) | pre-commit on every commit; Claude Code `PostToolUse` hook after each edit |
| `review-comments` | new comments, docstrings and `Field` descriptions say only what the code cannot (DOC-2 to DOC-7), judged by `claude -p` with a structured verdict | Claude Code `Stop` hook; `pre-commit run review-comments --hook-stage manual` |
| `check-protected` | files `.gitattributes` marks `protected` (generated, vendored, published) are not edited by hand (TOOL-5) | Claude Code `PreToolUse` hook before each edit |

Generated projects install it as a dev dependency pinned to the template's commit (a local path until this repo is
pushed) and wire both layers. Repos that don't use uv can use `.pre-commit-hooks.yaml` instead.

Projects also get two read-only subagents in `.claude/agents/`: `conventions-reviewer` checks a branch or the repo
against the guide, and `descriptions-judge` checks each config description and YAML comment against DOC-7 and the code.

`review-comments` and both subagents are LLM judges (TOOL-6). `tests/judges/` holds their labelled cases: diffs that
must pass or fail, and projects with planted mistakes. Rerun them after changing a judge's prompt or the model, and
add each mistake a judge makes as a new case.

```bash
make test             # unit tests of the hooks, under a second
make test-templates   # render every profile and run its checks (slow, needs network)
make test-judges      # the judges on their labelled cases (live `claude` calls: minutes, about $3)
```

## Start a project

```bash
uvx copier copy --data profile=rnd ~/Projects/Personal/conventions my-project
cd my-project
git init && make setup    # uv sync + pre-commit and commit-msg hooks
make github               # once the GitHub repo exists: squash-merge settings (GIT-3)
make check                # ruff, import contracts, pyright, pytest
```

```bash
uvx copier copy --data profile=uni ~/Projects/Personal/conventions iasa-course
cd iasa-course
git init && make setup
make lab N=001 TOPIC=genetic
```

Copier asks for the remaining answers: the project name, the Python version (default 3.14), and W&B for rnd or the
title-page fields for uni. Pass `--defaults` to accept them all.

## Update a project

Generated projects record the template version in `.copier-answers.yml`. Updating needs a tagged template commit:

```bash
copier update             # from the project root, with a clean working tree
```

Copier merges template changes with local edits and leaves conflicts as `.rej` files.

## Adopt the guide in an existing repo

1. Read the [quick reference](GUIDE.md#quick-reference) and list what the repo does differently under "Deviations"
   in its CONTRIBUTING.md.
2. Port the mechanical parts first, by rendering the template into a scratch directory and diffing:
   - pyproject tool blocks (ruff, pyright, pytest, import-linter);
   - `.pre-commit-config.yaml`, the Makefile and CI.
3. Then copy `src/nuikit/` and `tests/nuikit/` from the render, move the repo's paths into `<pkg>/paths.py`, and
   switch imports to `nuikit` one module at a time.
4. Then refactor rule by rule (attrs classes, generated configs, structlog events), one conventional commit per rule,
   citing its ID.

## Change a rule

1. Edit the rule in `GUIDE.md`, keeping its ID, and update every template it affects.
2. Run `make test-templates`. It renders every profile and runs each one's own `make check`; it takes about 30 s and
   needs network for `uv sync`.
3. Commit, then tag `vMAJOR.MINOR.PATCH` so projects can `copier update`.

## Known issues

- Python 3.14 needs `hydra-core>=1.4.0rc1`, a pre-release, because 1.3.x crashes on 3.14. Move the pin to 1.4.0 once
  it ships.
- The tests don't exercise the LaTeX toolchain (`make report`), because it needs Docker and TeX Live.

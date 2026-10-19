# AGENTS.md

This repo holds my coding conventions: `GUIDE.md` (the rules) and copier templates that implement them
(`templates/rnd`, `templates/uni`, `templates/lab`, sharing partials from `shared/`).

## Working here

- A rule change touches `GUIDE.md` and every template it affects, in the same commit. Keep the rule ID; never reuse
  a retired ID.
- Rules use RFC 2119 keywords in capitals, and each one has a *Why* and a *Check*. Prefer a check a tool can run.
- Templates must render and pass their own `make check` for every profile: run `make test-templates` before
  committing a template change. `make test` covers the hooks package.
- Generated projects follow `GUIDE.md` themselves, so template code is held to the same rules: attrs classes, one-line
  module docstrings, comments only for what code can't say, ASCII in `.py` files.
- Releases are git tags (`vMAJOR.MINOR.PATCH`). Projects pull changes with `copier update`, so a template change must
  keep `copier update` working on existing projects (no renamed questions without a migration).
- Commits follow GIT-1 and GIT-2: one line, Conventional Commits, lowercase imperative subject, no articles.

## Layout

```text
GUIDE.md          the rules
README.md         how to use the templates, the hooks and adopt the guide
src/conventions_hooks/   check-comments, review-comments (the conventions-hooks package)
.pre-commit-hooks.yaml   the same hooks for repos that consume this one through pre-commit
copier.yml        questions; `profile` selects templates/<profile>
shared/           Jinja partials included by several profiles
templates/        rnd, uni, lab
tests/            hooks/: unit tests (`make test`); test_templates.py: every profile renders and passes its checks
```

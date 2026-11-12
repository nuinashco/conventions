---
area: LAY
title: Layout and packaging
skill: layout-and-packaging
description: >-
  Use when creating a Python project or changing how it is packaged: pyproject.toml, requires-python, dependency
  groups and extras, the Makefile, or where a new top-level package or subpackage goes.
paths:
  - pyproject.toml
  - Makefile
  - .python-version
---

Which top-level folders a project has (LAY-4) and where its entry points live (LAY-7) are rules of
nuinashco/rnd-template, in the [`.claude/rules/`](https://github.com/nuinashco/rnd-template/tree/main/template/.claude/rules) it gives every project.

### LAY-1 MUST

Projects use uv with the `uv_build` backend, the src layout and a committed `uv.lock`.

*Why:* tests then run against the package as installed, not against the working tree
([Hynek](https://hynek.me/articles/testing-packaging/), [pytest](https://docs.pytest.org/en/stable/explanation/goodpractices.html));
`uv init` generates this layout by default.

*Check:* template.

### LAY-2 MUST

A distribution has one top-level import package, `src/<pkg>/`. A standalone part of the project (a proxy, a client) is
a subpackage such as `<pkg>/proxy/`, isolated by an import contract (ARC-1). There is no `utils/`, `common/`, `core/`
or `helpers/` grab bag: each module is named after its one responsibility. Extract a part into its own distribution
only when a second repo depends on it.

*Why:* uv supports several top-level modules but ["does not recommend this
structure"](https://docs.astral.sh/uv/concepts/build-backend/) because generic names like `common` collide in
site-packages; a distinctive name avoids that.

*Check:* `module-name = "<pkg>"` in the template; `check-conventions` flags grab-bag module names under `src/`, also
when private (`_utils.py`) or suffixed (`string_utils.py`).

### LAY-3 MUST

`requires-python` starts at the latest stable CPython when the project is created (3.14 as of 2026-10). Pin lower only
when a dependency or runtime forces it, and say which one in a comment next to the pin. A pre-release dependency is
acceptable when it is the first to support that Python, with the reason next to it: nuikit needs
`hydra-core>=1.4.0rc1` because 1.3.x crashes on 3.14.

*Check:* template default; review.

### LAY-5 SHOULD

Developer tools go in `[dependency-groups] dev`. Heavy optional features (GPU backends, trackers) are extras, and their
imports are lazy (ARC-8).

*Check:* review.

### LAY-6 MUST

A Makefile runs every routine task and documents itself: `make help` lists the targets from their `##` comments. The
standard targets are `setup lint format typecheck test check`, plus what the project needs, such as
`test-integration` and `configs` in an rnd project or `build` in a library.

*Why:* one memorable entry point for people, CI and agents.

*Check:* template.

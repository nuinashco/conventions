---
area: STY
title: Code style
skill: code-style
description: >-
  Use when writing or reviewing Python code for formatting, lint rules and noqa comments, imports, parameter order,
  naming, units in names, file paths, non-ASCII characters and function complexity.
paths:
  - "**/*.py"
  - pyproject.toml
---

### STY-1 MUST

Format with ruff format: 88 columns, double quotes.

*Why:* the ecosystem default, the most readable side by side, and inside the accessibility limit Black documents
([Black](https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html)).

*Check:* `ruff format --check`.

### STY-2 MUST

Lint with the template's curated rule set: `E F W I B UP SIM RET PTH C4 RUF TID FBT N PERF G LOG BLE PL D NPY ERA T20
C90` (plus `FA` below 3.14), with `ANN` for the signatures in `src/` (TYP-1), `PGH004` for a bare `# noqa` and `TD004`
to `TD007` for TODO comments (DOC-6). `D401` is selected explicitly, because the google docstring convention silently
drops it. Ignored on purpose: `PLR2004`, `PLR0913`, `PLC0415`, `ANN401`, `D102`, `D103`, `D105`, `D106`, `D107`. The
set changes only by changing this guide. A `# noqa` names the rule and gives a reason.

*Why:* an explicit select keeps upgrades from changing the rules silently ([ruff](https://docs.astral.sh/ruff/linter/)).

*Check:* `ruff check`, with PGH004 for the rule a `# noqa` names; review for its reason.

### STY-3 MUST

Imports are absolute.

*Check:* ruff TID252 with `ban-relative-imports = "all"`.

### STY-4 MUST

Every optional parameter and every boolean parameter is keyword-only (after `*`). Only the one or two obvious subjects
of a call are positional. A signature that a base class fixes is marked `@override` and keeps its shape; one that a
caller outside the project fixes (a resolver, a signal handler) waives the rule with its reason.

*Check:* ruff FBT for booleans; `check-conventions` flags a positional parameter with a default, except in an
`@override` method and before `/`; review for the rest.

### STY-5 MUST

Naming:

- Modules are short nouns (`harness`, `soundness`). Functions are verbs (`select`, `bind`).
- Classes are nouns, and family items carry the family suffix (`LiteLLMEndpoint`, `GoldPatches`).
- Schemas end in `Config`. Acronyms stay capitalised (`HDBSCANClustering`, `BQ2GCSCollector`).
- Constants are UPPER_SNAKE right after the imports.
- Anything not used outside its module starts with `_`.

*Check:* ruff N; review.

### STY-6 MUST

A name holding a number with a unit ends in a short unit suffix: `_s`, `_ms`, `_mb`, `_gb`, `_tokens`, `_steps`.
Minutes and hours are spelled out (`_minutes`, `_hours`), because `_min` reads as "minimum". A name that mirrors an
external format (a file another tool reads, a library's parameters, a CLI flag) keeps that format's spelling:
`timeout_seconds` in a scorer's config file, `max_model_len` from vLLM.

*Check:* review.

### STY-7 MUST

Use pathlib, never `os.path`.

*Check:* ruff PTH.

### STY-8 MUST

`.py` files are ASCII: use `;`, `:`, `-` and `->`, never em dashes or Unicode arrows. Markdown may use any typography.

*Why:* greppable and terminal-safe.

*Check:* `check-conventions` reports each line that has a character outside ASCII.

### STY-9 SHOULD

Prefer early returns to nesting, comprehensions to `map`/`filter`, and `match` for dispatch on a shape or a file
suffix.

*Check:* review.

### STY-10 SHOULD

Keep within the complexity budget (C901 at 10, pylint's branch and statement limits). Split long functions at real
seams, not into one-call helpers that are shallow modules
([Ousterhout](https://github.com/johnousterhout/aposd-vs-clean-code)).

*Check:* ruff C901, PLR0912, PLR0915.

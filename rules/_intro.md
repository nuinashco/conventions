---
title: Conventions guide
areas: [LAY, ARC, TYP, STY, DOC, ERR, LOG, TST, RDOC, GIT, TOOL]
retired: [GIT-4, UNI-1, UNI-2, UNI-3, UNI-4, UNI-5, UNI-6]
---

How I structure, write, test and document Python and ML projects. These are the rules every repo follows; the
`conventions` Claude Code plugin carries them to Claude, one skill per area, and the `conventions-hooks` package checks
what a tool can.

Version 0.1.0 · last reviewed 2026-11-05 · owner: nuinashco

## How to read

- **MUST**, **SHOULD** and **MAY** follow [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) as clarified by
  [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174): they carry their meaning only in capitals.
  - **MUST**: checked by a tool or test where possible. A justified exception gets a comment at the site naming the
    rule (`# noqa: BLE001 - a failing callback must not stop training`, or
    `# conventions: TYP-4 - the base class from httpx needs __init__.` for `check-conventions`).
  - **SHOULD**: the default. Deviate when you can say why.
  - **MAY**: a matter of taste, written down so it is consistent.
- Every rule has an ID (`STY-4`) for reviews and commit bodies, a *Why*, and a *Check*: a ruff rule, pyright, a hook
  of this repo, a test, `template` when [nuinashco/rnd-template](https://github.com/nuinashco/rnd-template) sets it
  up, or `review` when no tool can tell. [COVERAGE.md](COVERAGE.md) lists the MUST rules only review checks.
- Rules apply to every project unless tagged **[rnd]** (research and development: tools, pipelines, training).
- A repo that can't follow a rule yet lists it under "Deviations" in its CONTRIBUTING.md, with the reason. A rule that
  does not apply to the repo at all goes in `ignore` of its `[tool.conventions]` table (TOOL-4), and the hooks skip it.
- Changing a rule means editing it under `rules/` in nuinashco/conventions, regenerating this file and the plugin with
  `make build`, and changing the checks and templates it affects in the same commit, then tagging a new version.
  Projects pick it up through the plugin and by upgrading `conventions-hooks`.

## Where the other rules live

The IDs below belong to the repos that implement them, with the same shape.

| rules | repo | about |
|---|---|---|
| FAM-1 to FAM-5, CFG-1 to CFG-8, ERR-1, ERR-2, LOG-1, LOG-3, RUN-1, RUN-2 | [nuinashco/nuikit](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md) | the shared library: families, configs, errors, logging, run directories, seeding |
| LAY-4, LAY-7, ENV-1 to ENV-3, TST-5, RUN-3 to RUN-7, TOOL-3 | [nuinashco/rnd-template](https://github.com/nuinashco/rnd-template/tree/main/template/.claude/rules) | the project template: top-level layout, entry points, paths, invariant tests, reproducibility and data, `copier update` |

## Retired rules

IDs are never reused.

- GIT-4, retired on 2026-10-19: commit messages are one line, without trailers (GIT-2).
- UNI-1 to UNI-6, retired on 2026-11-05 with the uni course profile.

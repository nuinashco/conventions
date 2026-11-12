---
area: RDOC
title: Repository docs
skill: repository-docs
description: >-
  Use when writing or updating README.md, CONTRIBUTING.md, AGENTS.md, CLAUDE.md, .claude/rules or a diagram, and
  when a code change makes one of them stale.
paths:
  - "**/*.md"
---

### RDOC-1 MUST

README.md is the user's and operator's view: setup, daily workflow, commands, outputs, caveats. It opens by saying
in a sentence or two what the project is and who it is for, then shows how to install it and one command or snippet
to copy, with its output where that helps. A command block holds only what is typed: an interactive zsh hands a
trailing `# comment` to the command, so the explanation goes in the sentence beside the block. The README stays
short, about 100 lines, and links to what is longer.
CONTRIBUTING.md is the contributor's view: architecture, layout, families, configs, deviations, the "Extending"
table, tests, commits and releases.

*Why:* one document, one purpose ([SWE at Google ch. 10](https://abseil.io/resources/swe-book/html/ch10.html)). A
README is what a first-time reader meets, so it holds what they need to start and points to the rest
([Google's README guide](https://google.github.io/styleguide/docguide/READMEs.html),
[GitHub](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes),
[Standard Readme](https://github.com/RichardLitt/standard-readme/blob/main/spec.md)).

*Check:* template skeletons; review.

### RDOC-2 MUST

A standalone subpackage has its own README.md and CONTRIBUTING.md next to its code.

*Check:* review.

### RDOC-3 MUST

Diagrams are mermaid. Flowcharts colour pure components with `classDef pure` and effectful ones with `classDef side`,
using the template's palette. The main run gets one sequence diagram.

*Check:* template.

### RDOC-4 MUST

AGENTS.md is the entry point for coding agents, at most 60 lines: commands, layout, what this repo asks beyond the
conventions, and pointers to CONTRIBUTING. CLAUDE.md is `@AGENTS.md`, plus any Claude-only extras. The conventions
reach Claude through the `conventions` plugin of the `nuinashco` marketplace (its skills, its `conventions-reviewer`
and `descriptions-judge` subagents and its hooks, TOOL-4), and a project's own path-scoped rules live in
`.claude/rules/`. Agent files never copy this guide, and leave to linters what linters check.

*Why:* [agents.md](https://agents.md/); [Claude Code memory](https://code.claude.com/docs/en/memory) recommends short,
specific files, and a skill or a path-scoped rule loads only when its files are in play.

*Check:* template; review.

### RDOC-5 MUST

Docs change in the same commit as the code they describe. A stale doc is a bug.

*Check:* review.

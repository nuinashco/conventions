---
title: Decisions
---

Contested choices, what was weighed and why this guide picks what it does. Revisit an entry when its reason no longer
holds. The choices behind the shared library (families, the config bridge, config defaults, errors, logging) are in
[nuikit's guide](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md), and those behind the project layout in
[nuinashco/rnd-template](https://github.com/nuinashco/rnd-template).

| topic | decision | alternatives | why |
|---|---|---|---|
| line length | 88 | 79 (PEP 8, Google), 100, 120 (earlier repos) | ecosystem default; no primary guide endorses 120 |
| multi-part repos | one package with subpackages | uv workspace; several top-level modules | simplest, no name clashes; import-linter keeps the boundaries |
| shared building blocks | the `nuikit` library, a dependency pinned to a release tag | vendored by the template; copying by hand | one source with its own tags; a project takes a fix by moving one pin, not by a template update |
| rules for agents | written once in `rules/`, generated into this guide and the `conventions` plugin's skills and subagents | a copy of the guide in every project; hand-kept agent files | one source; every repo gets a new rule through the plugin, and Claude loads only the area it works in |
| config comments | only options and what the key can't say | a description on every field | comments that repeat the key bury the ones that matter |
| data classes | attrs for every class, pydantic for configs | dataclasses; pydantic everywhere | validation at the edge, plain typed state inside; no `__init__` boilerplate |
| interfaces | ABC families, Protocol seams | ABC only; Protocol only | registries need nominal bases; fakes need none |
| type checker | pyright standard, strict on libraries such as `nuikit` | mypy --strict; basedpyright; ty (beta) | checks unannotated code; understands attrs and pydantic natively |
| `__future__` annotations | always below 3.14, never from 3.14 | never; only where needed | consistent and automatic; follows PEP 649/749 |
| module docstrings | one line on every module | only `__init__` and CLI (earlier rule) | each module states its responsibility (PEP 257, Google) |
| test doubles | fakes, mocks banned | mocks at unmanaged edges (Khorikov) | tests don't couple to the implementation (SWE at Google ch. 13) |
| commits | standard types, imperative, one line, no articles | custom `doc`/`ref`; behaviour-as-fact subjects; bodies with the why | default tooling accepts them; git convention; terse history you can scan |
| merging | squash | rebase-merge; commit to main | messy branch history is fine; `main` stays one commit per change |
| Python | latest stable | 3.12 floor | newest language features; pin lower per project when forced |

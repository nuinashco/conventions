---
area: ARC
title: Architecture
skill: architecture
description: >-
  Use when adding, splitting or moving a module or subpackage, deciding where logic goes, wiring objects together in
  an entry point, choosing between a class and functions, or importing a heavy or optional library.
paths:
  - src/**/*.py
  - scripts/**/*.py
  - pyproject.toml
---

### ARC-1 MUST

Dependencies between a package's subpackages point one way, and the direction is declared as import-linter contracts
in `pyproject.toml`. A `layers` contract orders the subpackages from the entry points down to the lowest layer (such as
`paths`), and it is exhaustive, so a new subpackage fails `make check` until it is placed in a layer. A standalone
subpackage never imports the rest of the package except the lowest layer, and an explicit `forbidden` contract says
so, whatever layer it sits in. CONTRIBUTING draws the project's own layers.

*Why:* a module hides a design decision
([Parnas 1972](https://blog.acolyer.org/2016/09/05/on-the-criteria-to-be-used-in-decomposing-systems-into-modules/)).
Python has no package-private visibility, so a checked contract is the only way to keep a boundary
([Brown](https://simonbrown.je/modular-monolith)).

*Check:* `lint-imports` in `make check`.

### ARC-2 MUST

Every seam has a pure half that decides and an effectful half that acts: `plan.py` / `served.py`, `adapter.py` /
`runner.py`, `compiler.py` / `harness.py`. A dry run executes the pure half for real and logs what the effectful half
would do.

*Why:* functional core, imperative shell
([Bernhardt](https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell)). The pure half is
unit-tested without doubles, and the effectful half stays thin.

*Check:* review. CONTRIBUTING diagrams colour the two halves (RDOC-3).

### ARC-3 MUST

Each entry point has one composition root, where objects are built and wired: the `cli/<command>.py` function, or the
script itself. Everything else receives collaborators through constructor arguments. Module-level state is limited to
loggers, path constants and family registries.

*Why:* explicit dependencies replace patching in tests
([Cosmic Python ch. 13](https://www.cosmicpython.com/book/chapter_13_dependency_injection.html)).

*Check:* review.

### ARC-4 MUST

Code branches on declared capabilities, not identities. Use a `ClassVar[bool]` such as `requires_hardware`, or a method
that returns `None` when a feature is absent; never `if item.kind == "api"` or `isinstance(x, ConcreteItem)`.

*Why:* adding an item never edits its callers.

*Check:* `check-conventions` flags comparisons with a `kind` attribute; review for `isinstance`.

### ARC-5 SHOULD

Split the top level by domain (`evaluation/`, `grading/`, `endpoints/`) and split inside a domain by role.

*Why:* layers at the top level suit only small systems
([Fowler](https://martinfowler.com/bliki/PresentationDomainDataLayering.html)).

*Check:* review.

### ARC-6 SHOULD

Abstract on the third repetition, not the second. Until then prefer duplication: "duplication is far cheaper than the
wrong abstraction" ([Metz](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)).

*Check:* review.

### ARC-7 SHOULD

Use modules as namespaces: `from <pkg>.evaluation import harness`, then `harness.run(...)`. Write a class only when
there is state or polymorphism; otherwise write functions.

*Check:* review.

### ARC-8 MUST

Heavy or optional third-party modules (torch, vllm, litellm, cloud SDKs, wandb) are imported inside the function that
needs them. Annotations that name them use `if TYPE_CHECKING:` imports.

*Why:* CLI start-up time, test runtime, and optional extras.

*Check:* `check-conventions` flags a module-level import of a known heavy module under `src/`; review for the others;
ruff PLC0415 is off on purpose.

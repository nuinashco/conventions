---
area: ARC
title: Architecture
skill: architecture
description: >-
  Use when adding, splitting or moving a module or subpackage, deciding where logic goes, wiring objects together in
  an entry point, choosing between a class and functions, adding a variant (a kind, mode or backend), or importing a
  heavy or optional library.
paths:
  - src/**/*.py
  - scripts/**/*.py
  - pyproject.toml
---

Before writing new code, answer one question in the plan: when one more variant of what this code handles arrives (a
fifth metric, a second backend), which files change? Aim for one new file: a family item or a class beside the others.
Say which layer (ARC-1) and which seam half (ARC-2) each new module belongs to.

### ARC-1 MUST [rnd]

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

*Check:* `check-conventions` flags a `kind` attribute compared with a string, by `==`, `!=`, `in` or a `match` case;
review for `isinstance`.

### ARC-5 SHOULD

Split the top level by domain (`evaluation/`, `grading/`, `endpoints/`) and split inside a domain by role.

*Why:* layers at the top level suit only small systems
([Fowler](https://martinfowler.com/bliki/PresentationDomainDataLayering.html)).

*Check:* review.

### ARC-6 SHOULD

Extract shared code on the third repetition, not the second. Until then prefer duplication: "duplication is far cheaper
than the wrong abstraction" ([Metz](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)). This counts copies of
code, not variants of behaviour: a second switch on the same variant already calls for classes (ARC-9). A shared function
that needs one more parameter or branch to serve one more caller is the wrong abstraction: inline it back into its
callers, or split it per variant.

*Check:* review; `check-conventions` for the switches (ARC-9).

### ARC-7 SHOULD

Use modules as namespaces: `from <pkg>.evaluation import harness`, then `harness.run(...)`. Write a class when there is
state, or when behaviour varies by variant: interchangeable implementations of one role are classes behind one base or
`Protocol` (ARC-9), each small enough to read alone. Otherwise write functions; a class with only static methods, or
with one method and a constructor, is a function.

*Why:* functions are the cheapest unit until a second implementation appears; from then on the classes keep callers
from branching ([Hynek](https://hynek.me/articles/python-subclassing-redux/)).

*Check:* review.

### ARC-8 MUST

Heavy or optional third-party modules (torch, vllm, litellm, cloud SDKs, wandb) are imported inside the function that
needs them. Annotations that name them use `if TYPE_CHECKING:` imports. A module whose classes need one at import time,
as a model does for its `nn.Module` base, imports it at the top, and the code that uses that module imports it inside a
function in turn.

*Why:* CLI start-up time, test runtime, and optional extras.

*Check:* `check-conventions` flags a module-level import of a known heavy module under `src/`, unless a class base or a
decorator in the module uses it; review for the others; ruff PLC0415 is off on purpose.

### ARC-9 MUST

Behaviour that varies by variant is chosen in one place. A value that names a variant (a `kind`, `mode`, `backend` or
`strategy`, as a `str`, `Literal` or `StrEnum`) selects behaviour in at most one function: the factory that builds the
object for it. When a second function would branch on the same value, or one chain reaches three arms that run
different code, make each variant a class: a family item when a config selects it, otherwise a `Protocol` and one attrs
class per variant, chosen in the composition root (ARC-3). A chain that only maps values to constants is a dict. A
closed set that gains operations rather than variants (AST nodes, config shapes) stays a `match` that ends in
`assert_never`.

```python
# Bad: every new backend edits every function.
def start(cfg: RunConfig) -> None:
    if cfg.backend == "modal":
        ...
    elif cfg.backend == "local":
        ...


def cost_usd(cfg: RunConfig) -> float:
    return 0.3 if cfg.backend == "modal" else 0.0


# Good: a new backend is one new class.
class Backend(Protocol):
    def start(self) -> None: ...
    def cost_usd(self) -> float: ...
```

*Why:* every repeated switch is edited when a variant is added ("Repeated Switches",
[Fowler](https://martinfowler.com/books/refactoring.html)). Classes make new variants cheap and functions make new
operations cheap ([the expression problem](https://eli.thegreenplace.net/2016/the-expression-problem-and-its-solutions/)),
and research code mostly gains variants. Coding agents grow conditional chains rather than classes
([Zhu et al.](https://arxiv.org/html/2605.02741), [SlopCodeBench](https://arxiv.org/html/2603.24755v1)).

*Check:* `check-conventions` flags a variant name switched on with the same values in two functions of a package, and a
chain of three arms on one name. It leaves alone the factory, whose every arm builds an object, a `match` that ends in
`assert_never`, a value that does not read as a name (a file suffix, an empty string), and names that belong to other
libraries (`device.type`, a `dtype`, `sys.platform`). A switch waived by its comment does not count against the others.
Across modules it reads the package's folders that have an `__init__.py`, tests aside, and one of the two switches has
two arms or more; review for switches on `StrEnum` members, on `isinstance`, and through dicts of functions.

### ARC-10 SHOULD

A module, class or layer hides something its caller would otherwise know. Do not add a function or class that only
forwards its arguments, an interface with one implementation and no fake, or a layer whose names mirror the one below.

*Why:* deep modules have an interface much simpler than their implementation, and pass-through methods add no
functionality ([Ousterhout](https://github.com/johnousterhout/aposd-vs-clean-code)); ARC-9 must not turn into
abstraction for its own sake.

*Check:* `check-conventions` flags a module-level function under `src/` that takes parameters, gives none a default,
and only passes them, unchanged and in order, to another function of its package. Decorated functions, methods, a
public function over a private one, and calls that build an object or go through one are left alone; review for
one-implementation interfaces and mirrored layers.

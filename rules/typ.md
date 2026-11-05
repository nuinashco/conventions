---
area: TYP
title: Types and data
skill: types-and-data
description: >-
  Use when writing or changing a Python class, a type annotation, a data container or an interface: attrs classes,
  pydantic models, Protocols, ABCs, Literal and enum types, dicts that carry data.
paths:
  - "**/*.py"
---

### TYP-1 MUST

Every function signature in `src/` is annotated; test functions and fixtures may skip annotations. pyright in standard
mode passes on `src/` and `tests/`, and strict mode passes on the `src/` of a library other repos import, such as
nuikit.

*Why:* the code relies on types (generics, `ClassVar`, `Config` bindings) that only a checker verifies.

*Check:* `make typecheck`.

### TYP-2 MUST

Use modern syntax: `X | None`, builtin generics, `collections.abc` for abstract containers, PEP 695 generics and
`type` aliases.

*Check:* ruff UP.

### TYP-3 MUST

While `requires-python` is below 3.14, every module starts with `from __future__ import annotations`. From 3.14 on it
is never used: [PEP 649](https://peps.python.org/pep-0649/) makes annotations lazy, and
[PEP 749](https://peps.python.org/pep-0749/) schedules the import for deprecation.

*Check:* ruff I002 with `required-imports`, set by the template only for Python below 3.14.

### TYP-4 MUST

pydantic is only for data parsed from outside: configs, HTTP bodies, files. Every other class is an attrs class:
`@frozen` for values, `@define` for stateful objects, family bases and items included. Exceptions, factories (classes
that are never instantiated) and subclasses of third-party classes stay plain classes. Classes have no hand-written
`__init__`. Construction logic goes into a classmethod constructor, or into `__attrs_post_init__` when it only derives
private state.

```python
# Bad: construction does work in __init__.
class RateLimiter:
    def __init__(self, rpm: float | None) -> None:
        self.interval_s = 60.0 / rpm if rpm else 0.0
        self._lock = asyncio.Lock()


# Good: fields declare state; a named constructor derives it.
@define
class RateLimiter:
    """Spacing between requests to one upstream."""

    interval_s: float
    _lock: asyncio.Lock = field(factory=asyncio.Lock, init=False)

    @classmethod
    def per_minute(cls, rpm: float | None) -> RateLimiter:
        return cls(60.0 / rpm if rpm else 0.0)
```

*Why:* validation libraries belong at the boundary; inside, a class should only hold already-valid data
([attrs](https://www.attrs.org/en/stable/why.html), [Hynek](https://speakerdeck.com/hynek/design-pressure)).

*Check:* `check-conventions` flags a hand-written `__init__` and dataclasses; review for pydantic inside the boundary.

### TYP-5 MUST

Mind three attrs behaviours, each verified on attrs 26.1:

- `@define` builds a new class, so a registering decorator must be the outermost one
  ([FAM-2](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md#fam-2-must)).
- `__init_subclass__` runs twice for slotted classes, so hooks in it must be idempotent.
- Slots stop attribute typos only when every base class is slotted, which is why family bases are attrs classes too.

*Check:* `nuikit` registry tests.

### TYP-6 MUST

Family bases are ABCs: the registry checks subclassing, and items inherit `Config` and helpers. An injected
collaborator that only needs a shape (a clock, an HTTP client, an uploader) is typed as a `Protocol`, so fakes need no
inheritance.

*Why:* [Hynek, "Subclassing in Python Redux"](https://hynek.me/articles/python-subclassing-redux/).

*Check:* review.

### TYP-7 SHOULD

Use `Literal` for small closed sets of config values, and `StrEnum` when code iterates over the set or attaches
behaviour to it.

*Check:* review.

### TYP-8 SHOULD

Avoid `Any` outside JSON-shaped payloads and lazily imported third-party objects. Use `object` for "accepts anything".

*Check:* review.

### TYP-9 MUST

Dicts are for wire payloads only (JSON in, JSON out). A dict with a fixed set of known keys is a class.

*Check:* review.

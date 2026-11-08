---
area: TST
title: Tests
skill: tests
description: >-
  Use when writing, naming, splitting or moving tests, test doubles and fixtures, or adding a slow test.
paths:
  - tests/**
---

TST-5, the invariant tests every rnd project carries, is a rule of nuinashco/rnd-template, in the
[`.claude/rules/`](https://github.com/nuinashco/rnd-template/tree/main/template/.claude/rules) it gives every project.

### TST-1 MUST

Tests are pytest functions (no test classes) named as sentences stating a behaviour:
`test_sound_selection_never_falls_back_to_every_task`.

*Check:* `check-conventions` flags test classes; review for the names.

### TST-2 MUST

Unit tests come first. Each case covers a distinct branch or behaviour: no cross-product parametrisation, and nothing
re-tested at a higher level that a unit test already covers.

*Why:* test behaviour, one test per behaviour ([SWE at Google ch. 12](https://abseil.io/resources/swe-book/html/ch12.html)).

*Check:* review.

### TST-3 MUST

Test doubles are in-process fakes (`ScriptedEndpoint`, `httpx.MockTransport`), `tmp_path` and `monkeypatch`.
`unittest.mock` is banned. Fakes live in `tests/conftest.py` or `tests/fakes.py`; a fake with logic has its own tests.

*Why:* prefer real objects, then fakes; interaction testing couples tests to the implementation
([SWE at Google ch. 13](https://abseil.io/resources/swe-book/html/ch13.html),
[Fowler](https://martinfowler.com/articles/mocksArentStubs.html)).

*Check:* ruff `banned-api`.

### TST-4 MUST

The layout mirrors `src/` module by module: `tests/<pkg>/<sub>/test_<module>.py` for every module with branching logic.
Exempt modules are those with nothing a unit test could distinguish: schemas whose rules pydantic enforces, error
classes, re-exporting `__init__` files, and thin wrappers that only start an external process (a `docker build`). They
are covered by the invariants or the integration test. Cross-cutting invariants live in `tests/test_invariants.py`.
End-to-end tests live in `tests/integration/`, are marked `integration` and are deselected by default
(`-m integration` runs them).

*Check:* `--strict-markers`; review.

### TST-6 MUST

Child processes, servers and Docker appear only in tests of what can't be measured in process. Before adding a slow
test, check `pytest --durations=10`. The unit suite stays under about 10 s.

*Check:* review.

### TST-7 SHOULD

Separate arrange, act and assert with blank lines. Compare related values in one tuple assert. A test module's
docstring states the invariant it protects.

*Check:* review.

### TST-8 SHOULD

Test ML code with tiny real models, not mocks: loss decreases, and a batch can be overfitted
([Yan](https://eugeneyan.com/writing/unit-testing-ml/)).

*Check:* review.

---
paths:
  - "tests/**/*.py"
  - "src/**/config.py"
  - "src/**/base.py"
---

# Invariant tests

A rule of [nuinashco/rnd-template](https://github.com/nuinashco/rnd-template). How tests are named, laid out and
faked (TST-1 to TST-4, TST-6 to TST-8) comes with the `conventions` plugin.

### TST-5 MUST

The invariant tests check that:

- every entry config composes and validates;
- generated configs are fresh;
- the import contracts hold;
- every registered kind builds from its generated YAML.

*Check:* the template's `tests/test_invariants.py`.

---
area: ERR
title: Errors
skill: errors
description: >-
  Use when raising, translating or catching an exception, validating input before expensive work, or writing an error
  message.
paths:
  - src/**/*.py
  - scripts/**/*.py
---

ERR-1 and ERR-2, the `UserError` family with its exit codes and the one `@cli_boundary` per entry point, are rules of
[nuikit](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md).

### ERR-3 MUST

A message is lowercase with no trailing period. It states what is wrong, then `; ` and the remedy, naming the command or
config key. An unknown name lists the valid ones.

```text
error: no soundness data; run `g4swe-grade controls` first
error: unknown endpoint kind 'gemni'; registered: gemini, litellm, passthrough
```

*Check:* `check-conventions` flags a capitalised first word and a trailing period in a message of two words or more;
review for the remedy.

### ERR-4 MUST

Fail fast at the edge: check that paths exist, kinds are registered and credentials work (a one-token ping) before any
expensive work starts.

*Why:* [Shore, "Fail Fast"](https://www.martinfowler.com/ieeeSoftware/failFast.pdf).

*Check:* review.

### ERR-5 MUST

Translating an exception uses `raise ... from err`. A broad `except Exception` exists only at an isolation point, such
as a callback that must not stop training or a best-effort notification, and its `noqa` says why.

*Check:* ruff B904, BLE001.

### ERR-6 MAY

Messages are written at the raise site. Ruff's TRY003 and EM rules, which want them inside the class, are not selected.

*Check:* the rule set of STY-2 leaves out TRY003 and EM.

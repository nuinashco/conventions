---
area: DOC
title: Comments and docstrings
skill: comments-and-docstrings
description: >-
  Use when writing or reviewing a comment, a docstring, a TODO, a YAML comment or a pydantic Field description.
paths:
  - "**/*.py"
  - "**/*.yaml"
---

### DOC-1 MUST

Every module starts with a one-line docstring stating its single responsibility. A CLI module's or script's docstring
is its `--help` text and may add a usage block.

*Why:* "what is this file for" stays answerable and greppable, and keeps each module honest about its scope
([PEP 257](https://peps.python.org/pep-0257/)).

*Check:* ruff D100, D104.

### DOC-2 MUST

Docstrings are one line where possible:

- a function's is imperative ("Return the run directory for `name`."); `D401` checks this;
- a class's is a noun phrase saying what an instance represents ("Spacing between requests to one upstream.");
- every public class has one (`D101`);
- a function or method gets one when its name and signature don't already say it all.

*Check:* ruff D101, D401; `check-comments` flags a class docstring that opens with an order (`Return the ...`);
review.

### DOC-3 SHOULD

Add Google-style `Args:`, `Returns:` or `Raises:` sections only for what types can't express: units, shapes, valid
ranges, what `None` or an empty value means, and errors that are part of the contract.

*Check:* review.

### DOC-4 MUST

A comment explains what the code can't say:

- an external constraint;
- a non-obvious reason;
- a unit;
- where a value came from (cite the source);
- what `None` means.

Never restate the code, never use section banners, and never leave commented-out code.

```python
# Bad: restates the code.
# Perform clustering
labels = model.fit_predict(embeddings)

# Good: says what the code can't.
# Wildcard is mandatory: BigQuery extract rejects single-file URIs for tables over 1 GB.
uri = f"{workdir_uri}/part-*.parquet"
```

*Why:* "Comments that contradict the code are worse than no comments" ([PEP 8](https://peps.python.org/pep-0008/)).
Information that code can't express still needs writing down
([Ousterhout](https://github.com/johnousterhout/aposd-vs-clean-code)).

*Check:* ruff ERA001; `check-comments` flags banners; `review-comments` asks Claude whether new comments say anything
the code doesn't (the plugin's `Stop` hook, and `uv run review-comments` for the staged diff).

### DOC-5 MUST

Comments are sentences: capitalised and ending with a period. A sentence that opens with a lowercase name puts it in
backticks (`` `git` is not installed. ``). A comment a tool reads is not one: `# noqa`, `# type:`, a `# %%` cell
marker, a PEP 723 block.

*Check:* `check-comments`, in pre-commit and as a Claude Code `PostToolUse` hook on every edited `.py` file.

### DOC-6 SHOULD

A `TODO` says why it isn't done now. Code generated without review is marked as such until reviewed.

*Check:* ruff TD004 to TD007 (a `TODO:` with a description); review for the why.

### DOC-7 MUST

A YAML comment, and so a `Field` description that a mirror turns into one
([CFG-3](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md#cfg-3-must)), lists a setting's options
(`auto|console|json`) or says what its key and value can't: a unit the name lacks, what `null` or an edge value means,
a side effect, a source. It never repeats the key: `wandb_project: x  # W&B project` says nothing.

*Why:* when every line has a comment, readers skip them all and the few that matter go unread; DOC-4, applied to
configs.

*Check:* `review-comments` on new descriptions; the `descriptions-judge` subagent, which checks each one against the
code.

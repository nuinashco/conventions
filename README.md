# conventions

Rules for Python and ML repos, the checks that enforce them, and a Claude Code plugin that teaches them to Claude.

| part | what it is |
|---|---|
| [GUIDE.md](GUIDE.md) | Every rule, with the tool that checks it and the reason where one is needed. |
| `conventions-hooks` | The checks, as commands. They run in `make check`, in pre-commit and while Claude edits. |
| `conventions` plugin | A skill per rule area, two review subagents, and hooks that run the checks on each edit. |

Starting a new project? Use [rnd-template](https://github.com/nuinashco/rnd-template), which sets all of this up.
The steps below add the conventions to a repo that already exists.

## Install

You need [uv](https://docs.astral.sh/uv/), and the repo's `requires-python` must start at 3.12 or later.

1. Add the checks to the repo, pinned to a release:

   ```bash
   uv add --dev git+https://github.com/nuinashco/conventions --tag v0.1.0
   ```

   A repo that also supports older Pythons adds `--marker "python_version >= '3.12'"` to that command: the checks
   then install on 3.12 and later only.

2. Opt the repo in, in its root `pyproject.toml`. The nearest `pyproject.toml` above a file decides, so a
   workspace member with its own `pyproject.toml` needs its own table:

   ```toml
   [tool.conventions]
   ```

3. Add the plugin to Claude Code, once per machine:

   ```text
   /plugin marketplace add nuinashco/conventions
   /plugin install conventions@nuinashco
   ```

   The plugin follows this repo's `main` branch. To have it update itself, turn on auto-update for the `nuinashco`
   marketplace in `/plugin`, or copy `extraKnownMarketplaces` from
   [rnd-template's settings](https://github.com/nuinashco/rnd-template/blob/main/template/.claude/settings.json).

## Use

Run a check on any files. Each finding names its rule, which [GUIDE.md](GUIDE.md) explains:

```console
$ uv run check-conventions src/demo/worker.py
src/demo/worker.py:4: STY-4 optional parameter `retries` goes after `*`, keyword-only
src/demo/worker.py:6: ARC-4 branch on a declared capability (`ClassVar[bool]`), not on `kind`
src/demo/worker.py:7: ERR-3 error messages start lowercase
src/demo/worker.py:7: ERR-3 error messages have no trailing period
```

| command | checks |
|---|---|
| `check-comments` | Comments are sentences, there are no section banners, class docstrings are noun phrases. |
| `check-conventions` | The code rules an AST can decide, such as attrs classes, keyword-only options and one switch per variant. |
| `check-commit-msg` | A commit message is one line of at most 72 characters: lowercase, no final period, no articles. |
| `check-protected` | Generated, vendored and published files are not edited by hand. |
| `review-comments` | New comments and docstrings in the staged diff say only what the code cannot. It asks Claude (`claude -p`). |

### Run them automatically

- **In `make check` and CI.** Add both checks to the `lint` target, on every Python file git does not ignore:

  ```make
  PYTHON_FILES = git ls-files -z -co --exclude-standard '*.py'

  lint:
  	$(PYTHON_FILES) | xargs -0 uv run check-comments
  	$(PYTHON_FILES) | xargs -0 uv run check-conventions
  ```

- **In pre-commit.** Add them as local hooks, so they run the version `uv.lock` pins. The first line makes
  `pre-commit install` add the commit-msg hook as well:

  <details>
  <summary><code>.pre-commit-config.yaml</code></summary>

  ```yaml
  default_install_hook_types: [pre-commit, commit-msg]
  repos:
    - repo: local
      hooks:
        - id: check-comments
          name: comments are sentences, no banners (GUIDE DOC)
          entry: uv run check-comments
          language: system
          types: [python]
        - id: check-conventions
          name: code rules an AST can decide (GUIDE)
          entry: uv run check-conventions
          language: system
          types: [python]
        - id: check-commit-msg
          name: commit message is one line without articles (GUIDE GIT-1, GIT-2)
          entry: uv run check-commit-msg
          language: system
          stages: [commit-msg]
  ```

  </details>

- **While Claude edits.** The plugin does this by itself, with the repo's own `.venv/bin/<command>`:
  `check-protected` before an edit, `check-comments` and `check-conventions` after it, and `review-comments` in the
  background once Claude hands back. That review is one `claude -p` call on your account, made only after a turn
  that left new comments; `REVIEW_COMMENTS_MODEL` picks its model, and listing DOC-2 to DOC-7 in `ignore` turns
  it off. The plugin does nothing in a repo without the `[tool.conventions]` table.

### Turn a rule off

- For the whole repo, list it in the table: `ignore = ["ENV-1", "ENV-3"]`.
- For one line, name the rule and the reason in a comment on that line or the one above:
  `# conventions: TYP-4 - the base class from httpx needs __init__.`

## Related repos

- [nuikit](https://github.com/nuinashco/nuikit): the library projects build on, with its own rules and plugin.
- [rnd-template](https://github.com/nuinashco/rnd-template): the template that starts a project with all three.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers the layout, how to change or add a rule, the tests and releases.

## License

[MIT](LICENSE)

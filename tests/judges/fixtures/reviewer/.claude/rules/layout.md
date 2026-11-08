---
paths:
  - "src/**/*.py"
  - "scripts/**"
  - "notebooks/**"
  - "configs/**/*.yaml"
  - "pyproject.toml"
  - ".gitignore"
  - ".env.example"
  - ".copier-answers.yml"
---

# Layout, paths and environment

Rules of [nuinashco/rnd-template](https://github.com/nuinashco/rnd-template), which made this project. The rules for
every repo come with the `conventions` plugin ([nuinashco/conventions](https://github.com/nuinashco/conventions));
FAM, CFG, ERR-1, ERR-2, LOG-1, LOG-3, RUN-1 and RUN-2 with the `nuikit` plugin
([nuinashco/nuikit](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md)).

This project's import layers (ARC-1), top to bottom, as the exhaustive contract in `pyproject.toml` declares them:
`cli` > `config` > `paths`. A new domain goes between `config` and `paths`; domains that don't import each other share
one layer as siblings (`"a | b"`).
`make check` fails until a new subpackage is placed.

### LAY-4 MUST

The top level holds at least `configs/` (Hydra YAML), `src/`, `tests/` and `notebooks/`, and optionally `scripts/`
(one-off runnables, LAY-7). Other top-level folders are allowed for what is not Python: product content (an agent's
prompts, a submission) or vendored artifacts (wheels, gitignored). The layout tree in CONTRIBUTING explains each one.
`data/`, `runs/`, `dist/` and `.env` are gitignored. `.env.example`, `.project-root` and `.python-version` are
committed.

*Check:* template `.gitignore`; review of the layout tree.

### LAY-7 MUST

Entry points live by lifecycle, not by the kind of task: the same data preparation is a command in one repo and a
script in another.

- A console script, one module in `<pkg>/cli/` registered in `[project.scripts]`, is anything the workflow depends
  on: `make` or CI runs it, it is rerun whenever its inputs change, its output is committed or checked by a test, or
  the README documents it for users.
- A file in `scripts/` is exploratory or one-time: a number or figure for a note, an idea being tried, a paper result
  reproduced once. It is Python or shell, never imported, and free to declare its own extra dependencies with PEP 723
  inline metadata. It may import the package and compose `configs/` with Hydra; a script that makes runs starts them
  as commands do (RUN-1).
- Either way, logic that more than one entry point needs lives in the package, and the entry point only wires it
  (ARC-3).
- When a script is rerun, shared or needs a test, it becomes a `cli/` command.
- A one-time conversion of frozen inputs, such as a published dataset turned into a committed table, stays a script
  although a test checks its output, when that output is committed with the sha256 of its inputs and of the script.
  The test checks the pin, a command runs the same check, and a changed input or script names the script to rerun.
- Not commands: a standalone subpackage's `__main__.py` that its own code starts as a child process stays inside that
  subpackage, and shell scripts meant for another machine (a GPU box) stay in `scripts/` even when the README mentions
  them.

*Why:* commands inside the package are importable, so they are tested in process (click's `CliRunner`, Hydra's
`compose`) and sit in the import-layer contract; one-off scripts stay out of the package and its API.

*Check:* review; ruff and pyright cover `scripts/` too.

### ENV-1 MUST

The repo root is found with rootutils and the `.project-root` marker. `<pkg>/paths.py` defines
`ROOT = rootutils.find_root(search_from=__file__, indicator=".project-root")` and UPPER_SNAKE constants with `_DIR` or
`_PATH` suffixes. Never `Path(__file__).parents[n]`, never paths relative to the working directory.

*Why:* scripts, tests, notebooks and Hydra all resolve the same root (the lightning-hydra-template convention).

*Check:* `check-conventions` flags a path climbed from `__file__`; review.

### ENV-2 MUST

Every entry point calls `rootutils.setup_root(__file__, indicator=".project-root")`, which loads `.env` and sets
`PROJECT_ROOT`. YAML refers to `${oc.env:PROJECT_ROOT}`.

*Check:* template entry points.

### ENV-3 MUST

Environment variables are read in YAML (`oc.env`) or in `<pkg>/paths.py`, never through `os.environ` scattered in
modules.

*Check:* `check-conventions` flags `os.environ` and `os.getenv` outside `paths.py` and tests.

### TOOL-3 MUST

A generated project keeps its `.copier-answers.yml` and pulls template changes with `copier update --trust`, from a
clean working tree. `--trust` lets the template's migrations run, such as the one that removes files a release no
longer ships.

*Check:* review.

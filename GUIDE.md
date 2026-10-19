# Conventions guide

How I structure, write, test and document Python and ML projects. The `rnd` and `uni` copier templates in this repo
implement these rules; this file explains them.

Version 0.1.0 · last reviewed 2026-10-18 · owner: nuinashco

- [How to read](#how-to-read) · [Quick reference](#quick-reference)
- [Layout](#1-layout-and-packaging-lay) · [Architecture](#2-architecture-arc) · [Families](#3-families-fam) ·
  [Configuration](#4-configuration-cfg) · [Paths](#5-paths-and-environment-env) · [Types and data](#6-types-and-data-typ)
- [Style](#7-code-style-sty) · [Comments](#8-comments-and-docstrings-doc) · [Errors](#9-errors-err) ·
  [Logging](#10-logging-log) · [Tests](#11-tests-tst) · [Runs](#12-runs-reproducibility-and-notebooks-run)
- [Repo docs](#13-repository-docs-rdoc) · [Git](#14-git-git) · [Tooling](#15-tooling-tool) · [uni](#16-uni-profile-uni)
- [Decisions](#decisions) · [Sources](#sources)

## How to read

- **MUST**, **SHOULD** and **MAY** follow [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) as clarified by
  [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174): they carry their meaning only in capitals.
  - **MUST**: checked by a tool or test where possible. A justified exception gets a comment at the site naming the
    rule (`# noqa: BLE001 - a failing callback must not stop training`).
  - **SHOULD**: the default. Deviate when you can say why.
  - **MAY**: a matter of taste, written down so it is consistent.
- Every rule has an ID (`CFG-3`) for reviews and commit bodies, a *Why*, and a *Check*: a ruff rule, pyright, a test
  in the template, or `review` when no tool can tell.
- Rules apply to every project unless tagged **[rnd]** (research and development: tools, pipelines, training) or
  **[uni]** (course labs).
- A repo that can't follow a rule yet lists it under "Deviations" in its CONTRIBUTING.md, with the reason.
- Changing a rule means changing this file and the templates in the same commit, then tagging a new version.
  Projects pick it up with `copier update`.

## Quick reference

| area | rule |
|---|---|
| project | uv, `uv_build`, src layout, one import package, latest stable Python, `make help` |
| entry points | interface commands in `<pkg>/cli/` (console scripts), one-off runnables in `scripts/` |
| architecture | import-linter contracts, pure/side-effect split, one composition root, capabilities not identities |
| extension points | family = `base.py` + `items/`, `@Factory.register(kind)` outermost, auto-discovered |
| config | Hydra composes, `Schema.from_hydra` validates (forbid + frozen), defaults in `Field` mirrored to `defaults/` and `kinds/`, hand-written entry configs and presets on top |
| paths | rootutils + `.project-root`, `<pkg>/paths.py` constants, `setup_root` in entry points |
| types | annotated everywhere, pyright standard (strict on `nuikit`), attrs for every class, pydantic only for configs |
| style | ruff format at 88, curated ruff rules, absolute imports, keyword-only options, unit suffixes, ASCII in `.py` |
| comments | one-line module docstring everywhere, one-line docstrings, comments only for what code can't say; checked by `check-comments` and `review-comments` |
| errors | `nuikit.errors.UserError` with `exit_code`, one `cli_boundary`, `lowercase message; remedy` |
| logging | structlog over stdlib, `log.info("snake_case_event", key=value)`, console in a TTY, JSON otherwise |
| tests | sentence names, unit-first, fakes not mocks, mirror `src/` per module, invariants, `-m integration` |
| runs | `runs/<name>/` with config, git SHA and outputs; seed once, pass generators; pin revisions |
| docs | README for users, CONTRIBUTING for contributors, mermaid with pure/side colours, AGENTS.md + CLAUDE.md |
| git | Conventional Commits, one-line imperative lowercase subjects without articles, short branches, squash-merge (`make github`), PR template |

## 1. Layout and packaging (LAY)

**LAY-1 MUST.** Projects use uv with the `uv_build` backend, the src layout and a committed `uv.lock`.
*Why:* tests then run against the package as installed, not against the working tree
([Hynek](https://hynek.me/articles/testing-packaging/), [pytest](https://docs.pytest.org/en/stable/explanation/goodpractices.html));
`uv init` generates this layout by default. *Check:* template.

**LAY-2 MUST.** A repo builds one distribution with two top-level import packages: the project's own, `src/<pkg>/`,
and `src/nuikit/`, the shared machinery the template copies in (config base, YAML generation, registry, errors,
logging, run directories, seeding) with its tests in `tests/nuikit/`. `nuikit` never imports `<pkg>`, and it is
changed upstream in the conventions repo and pulled with `copier update`, never edited in place. A standalone part
of the project (a proxy, a client) is a subpackage such as `<pkg>/proxy/`, isolated by an import contract (ARC-1).
There is no `core/`, `common/` or `utils/` grab bag. Extract a part into its own distribution only when a second
repo depends on it. *Why:* project code reads without template plumbing in it, and the seam shows in every import
block (STY-3 gives `nuikit` its own isort section). uv supports several top-level modules but ["does not recommend
this structure"](https://docs.astral.sh/uv/concepts/build-backend/) because generic names like `common` collide in
site-packages; a distinctive name avoids that. *Check:* `module-name = ["<pkg>", "nuikit"]`; `lint-imports` keeps
`nuikit` from importing `<pkg>` [rnd]; `check-protected` refuses agent edits to it (TOOL-5).

**LAY-3 MUST.** `requires-python` starts at the latest stable CPython when the project is created (3.14 as of
2026-10). Pin lower only when a dependency or runtime forces it, and say which one in a comment next to the pin.
A pre-release dependency is acceptable when it is the first to support that Python, with the reason next to it:
the templates need `hydra-core>=1.4.0rc1` because 1.3.x crashes on 3.14. *Check:* template default; review.

**LAY-4 MUST.** The top level holds at least `configs/` (Hydra YAML), `src/`, `tests/` and `notebooks/`, and
optionally `scripts/` (one-off runnables, LAY-7). Other top-level folders are allowed for what is not Python: product
content (an agent's prompts, a submission) or vendored artifacts (wheels, gitignored). The layout tree in
CONTRIBUTING explains each one. `data/`, `runs/`, `dist/` and `.env` are gitignored. `.env.example`, `.project-root`
and `.python-version` are committed. *Check:* template `.gitignore`; review of the layout tree.

**LAY-5 SHOULD.** Developer tools go in `[dependency-groups] dev`. Heavy optional features (GPU backends, trackers) are
extras, and their imports are lazy (ARC-8).

**LAY-6 MUST.** A Makefile runs every routine task and documents itself: `make help` lists the targets from their `##`
comments. The standard targets are `setup lint format typecheck test test-integration configs check`.
*Why:* one memorable entry point for people, CI and agents. *Check:* template.

**LAY-7 MUST.** Entry points live by role.

- A command that is part of the repo's interface (documented in the README, run by `make`, worth a test) is a
  console script: one module in `<pkg>/cli/`, registered in `[project.scripts]`.
- Anything run once or by hand (an experiment, data preparation, an analysis, a sweep) is a file in `scripts/`:
  Python or shell, never imported, and free to declare its own extra dependencies with PEP 723 inline metadata.
- When a script is reused or needs a test, it becomes a `cli/` command.
- **[uni]** A lab's pipeline steps are scripts (UNI-2): each one is run by hand for that lab.
- Not commands: a standalone subpackage's `__main__.py` that its own code starts as a child process stays inside that
  subpackage, and shell scripts meant for another machine (a GPU box) stay in `scripts/` even when the README
  mentions them.

*Why:* commands inside the package are importable, so they are tested in process (click's `CliRunner`, Hydra's
`compose`) and sit in the import-layer contract; one-off scripts stay out of the package and its API.
*Check:* review; ruff and pyright cover `scripts/` too.

## 2. Architecture (ARC)

**ARC-1 MUST [rnd].** Dependencies point one way, and the direction is declared as import-linter contracts in
`pyproject.toml`: `cli` → `config` → app modules → `paths`, and any layer may import `nuikit`, which never imports
`<pkg>`. A standalone subpackage never imports the rest of the package except `paths`, and an explicit `forbidden`
contract says so, whatever layer it sits in. The layers contract is exhaustive, so a new subpackage fails `make check` until it is placed in a layer.
*Why:* a module hides a design decision ([Parnas 1972](https://blog.acolyer.org/2016/09/05/on-the-criteria-to-be-used-in-decomposing-systems-into-modules/)).
Python has no package-private visibility, so a checked contract is the only way to keep a boundary
([Brown](https://simonbrown.je/modular-monolith)). *Check:* `lint-imports` in `make check`.

**ARC-2 MUST.** Every seam has a pure half that decides and an effectful half that acts: `plan.py` / `served.py`,
`adapter.py` / `runner.py`, `compiler.py` / `harness.py`. A dry run executes the pure half for real and logs what the
effectful half would do. *Why:* functional core, imperative shell
([Bernhardt](https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell)). The pure half
is unit-tested without doubles, and the effectful half stays thin. *Check:* review. CONTRIBUTING diagrams colour the
two halves (RDOC-3).

**ARC-3 MUST.** Each entry point has one composition root, where objects are built and wired: the `cli/<command>.py`
function, or the script itself. Everything else receives collaborators through constructor arguments. Module-level state is limited to
loggers, path constants and family registries.
*Why:* explicit dependencies replace patching in tests
([Cosmic Python ch. 13](https://www.cosmicpython.com/book/chapter_13_dependency_injection.html)). *Check:* review.

**ARC-4 MUST.** Code branches on declared capabilities, not identities. Use a `ClassVar[bool]` such as
`requires_hardware`, or a method that returns `None` when a feature is absent; never `if item.kind == "api"` or
`isinstance(x, ConcreteItem)`. *Why:* adding an item never edits its callers. *Check:* review (grep `kind ==`).

**ARC-5 SHOULD.** Split the top level by domain (`evaluation/`, `grading/`, `endpoints/`) and split inside a domain by
role. *Why:* layers at the top level suit only small systems
([Fowler](https://martinfowler.com/bliki/PresentationDomainDataLayering.html)).

**ARC-6 SHOULD.** Abstract on the third repetition, not the second. Until then prefer duplication: "duplication is far
cheaper than the wrong abstraction" ([Metz](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)).

**ARC-7 SHOULD.** Use modules as namespaces: `from <pkg>.evaluation import harness`, then `harness.run(...)`. Write a
class only when there is state or polymorphism; otherwise write functions.

**ARC-8 MUST.** Heavy or optional third-party modules (torch, vllm, litellm, cloud SDKs, wandb) are imported inside
the function that needs them. Annotations that name them use `if TYPE_CHECKING:` imports.
*Why:* CLI start-up time, test runtime, and optional extras. *Check:* review; ruff PLC0415 is off on purpose.

## 3. Families (FAM)

A family is any concept with several interchangeable implementations chosen by a config `kind`: endpoints, patch
sources, collectors, processors.

```text
<pkg>/endpoints/
  base.py            Endpoint (abstract), EndpointConfig, EndpointFactory
  items/
    __init__.py      import_submodules(__name__)
    passthrough.py   @EndpointFactory.register("passthrough")
    litellm.py       @EndpointFactory.register("litellm")
```

**FAM-1 MUST.** A family is `base.py` (abstract base, its config schema, its factory) plus an `items/` folder with one
module per implementation. `items/__init__.py` calls `nuikit.registry.import_submodules(__name__)`, so adding an item is
adding a file. The family's `__init__.py` imports `items`, so importing the family registers its kinds.
`make configs` and the invariant tests import the whole package (`nuikit.registry.import_tree`), so they see every
family even before code uses it. *Check:* review.

**FAM-2 MUST.** Items register with `@<Family>Factory.register("<kind>")` as the **outermost** decorator. Kinds are
snake_case and unique; registering a kind twice raises. *Why:* attrs replaces a slotted class, so a decorator applied
before `@define` would register the discarded class (TYP-5). *Check:* `nuikit` registry tests; review.

**FAM-3 MUST.** An item binds its config schema through the family's type argument:
`class Square(Shape[SquareConfig])` sets `Square.Config` and types `self.config` precisely. An explicit
`Config = X` still wins. `<Family>Factory.from_config(data)` reads `kind`, validates the rest against that item's
`Config` and builds the item (config-first creation); `validate(data)` only validates. *Check:* registry tests;
pyright.

**FAM-4 MUST.** Each factory declares `config_group`. `make configs` writes `configs/<group>/kinds/<kind>.yaml` for
every registered kind (CFG-3). *Check:* `tests/test_invariants.py` fails on stale or missing files.

**FAM-5 SHOULD.** CONTRIBUTING's "Extending" table lists every family: what to add, where, and what selects it.

Registration through eager auto-import is a deliberate choice at this scale. Its known costs are import time, the global
registry, and breakage under [PEP 810](https://peps.python.org/pep-0810/) lazy imports
([Wu](https://ppwwyyxx.com/blog/2023/Registration-Does-Not-Scale-Well/)). If import time becomes a problem, switch the
family to a lazy `kind -> "module:Class"` map.

## 4. Configuration (CFG)

**CFG-1 MUST.** Hydra composes YAML; the entry point validates the composed config with
`MainConfig.from_hydra(cfg)` before anything runs. No `DictConfig` travels past the entry point, and YAML never names
Python classes (`_target_`). *Why:* configs are parsed at the boundary
([King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/)); renames can't break YAML.
*Check:* `tests/test_invariants.py` composes and validates every entry config.

**CFG-2 MUST.** Schemas extend `nuikit.config.Schema` (`extra="forbid"`, `frozen=True`). A typo is an error with one line
per bad field, and validated configs are read-only. Pydantic's default coercion stays on. *Why:* "it should be
possible to detect unused or redundant settings"
([Sculley et al. 2015](https://papers.nips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html)).
*Check:* `nuikit` config tests.

**CFG-3 MUST.** Defaults and documentation live in the schema: `Field(default, description="... (seconds)")`.
`make configs` renders each schema to a mirror: every field, its default (or `???`) and its description as a comment.
Mirrors are committed and never edited, so the YAML shows what is tunable without opening Python. An entry config's
mirror is `configs/defaults/<command>.yaml` and leaves out the fields that config groups provide; a family item's
mirror is `configs/<group>/kinds/<kind>.yaml`. Everything else is hand-written, composes a mirror and only sets values:
the entry config `configs/<command>.yaml`, whose defaults list picks the mirror, the groups and Hydra's settings with
`_self_` last, and the presets in each group. A value changes in the narrowest place that fits:

| to change | edit |
|---|---|
| one run | `key=value` on the command line; the run directory records it |
| a reusable variant of one part | a preset in its group (`configs/endpoint/gemini.yaml`) |
| every run of this repo | the entry config `configs/<command>.yaml` |
| the default itself, which tests and Python callers also get | the schema, then `make configs` |

*Why:* defaults have one source, and every file is plainly either generated or yours to edit.
*Check:* `tests/test_invariants.py` fails when a mirror is stale, and composes every entry config with its mirror.

```python
class LiteLLMConfig(RemoteEndpointConfig):
    """Endpoint that calls a provider through LiteLLM."""

    model: str = Field(description="LiteLLM model string")
    rpm: PositiveInt | None = Field(
        None, description="requests per minute; null = unlimited"
    )
    timeout_s: PositiveFloat = Field(600, description="per-request timeout")
```

```yaml
# Generated by `make configs` from LiteLLMConfig; edit the schema, not this file.
kind: litellm
model: ???        # LiteLLM model string
rpm: null         # requests per minute; null = unlimited
timeout_s: 600    # per-request timeout
```

**CFG-4 MUST.** A value with no sensible default has no default in the schema and is `???` in YAML. Never use a
placeholder value. *Check:* review.

**CFG-5 MUST.** The config tree mirrors the code:

- a family selected through config has a group `configs/<config_group>/` ↔ `<pkg>/<family>/`;
- each entry config `configs/<command>.yaml` and its mirror `configs/defaults/<command>.yaml` ↔ a schema in
  `<pkg>/config.py` (or a `<pkg>/config/` package once there are several);
- a group of presets for one schema (`configs/eval/`) ↔ that schema.

A family chosen by a CLI argument rather than by config needs no group. *Check:* review.

**CFG-6 MUST.** Secrets come from the environment (`.env`, loaded by `rootutils.setup_root`) through
`${oc.env:VAR,null}`. They are typed `SecretStr`, are never written to disk unmasked, and reach child processes through
the environment. *Check:* the run snapshot test masks secrets; gitleaks.

**CFG-7 MUST.** Anything a user might tune comes from config. Constants in code are for facts: protocol limits,
measured values, unit conversions. Each one gets a comment giving its provenance. *Check:* review.

**CFG-8 SHOULD.** A polymorphic config field resolves through its family factory by `kind`; an unknown kind lists the
registered ones in its error.

## 5. Paths and environment (ENV)

**ENV-1 MUST.** The repo root is found with rootutils and the `.project-root` marker. `<pkg>/paths.py` defines
`ROOT = rootutils.find_root(search_from=__file__, indicator=".project-root")` and UPPER_SNAKE constants with `_DIR` or
`_PATH` suffixes. Never `Path(__file__).parents[n]`, never paths relative to the working directory.
*Why:* scripts, tests, notebooks and Hydra all resolve the same root (the lightning-hydra-template convention).
*Check:* review.

**ENV-2 MUST.** Every entry point calls `rootutils.setup_root(__file__, indicator=".project-root")`, which loads
`.env` and sets `PROJECT_ROOT`. YAML refers to `${oc.env:PROJECT_ROOT}`. *Check:* template entry points.

**ENV-3 MUST.** Environment variables are read in YAML (`oc.env`) or in `<pkg>/paths.py`, never through `os.environ`
scattered in modules. *Check:* review (grep `os.environ`).

## 6. Types and data (TYP)

**TYP-1 MUST.** Every function signature in `src/` is annotated; test functions and fixtures may skip annotations.
pyright in standard mode passes on `src/` and `tests/`, and strict mode passes on `nuikit/`. *Why:* the code relies on
types (generics, `ClassVar`, `Config` bindings) that only a checker verifies. *Check:* `make typecheck`.

**TYP-2 MUST.** Use modern syntax: `X | None`, builtin generics, `collections.abc` for abstract containers, PEP 695
generics and `type` aliases. *Check:* ruff UP.

**TYP-3 MUST.** While `requires-python` is below 3.14, every module starts with `from __future__ import annotations`.
From 3.14 on it is never used: [PEP 649](https://peps.python.org/pep-0649/) makes annotations lazy, and
[PEP 749](https://peps.python.org/pep-0749/) schedules the import for deprecation. *Check:* ruff I002 with
`required-imports`, set by the template only for Python below 3.14.

**TYP-4 MUST.** pydantic is only for data parsed from outside: configs, HTTP bodies, files. Every other class is an
attrs class: `@frozen` for values, `@define` for stateful objects, family bases and items included. Exceptions,
factories (classes that are never instantiated) and subclasses of third-party classes stay plain classes. Classes have no hand-written `__init__`. Construction logic goes into a classmethod constructor, or into `__attrs_post_init__` when it
only derives private state. *Why:* validation libraries belong at the boundary; inside, a class should only hold
already-valid data ([attrs](https://www.attrs.org/en/stable/why.html), [Hynek](https://speakerdeck.com/hynek/design-pressure)).
*Check:* review (grep `def __init__`).

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

**TYP-5 MUST.** Mind three attrs behaviours, each verified on attrs 26.1:

- `@define` builds a new class, so a registering decorator must be the outermost one (FAM-2).
- `__init_subclass__` runs twice for slotted classes, so hooks in it must be idempotent.
- Slots stop attribute typos only when every base class is slotted, which is why family bases are attrs classes too.

*Check:* `nuikit` registry tests.

**TYP-6 MUST.** Family bases are ABCs: the registry checks subclassing, and items inherit `Config` and helpers. An
injected collaborator that only needs a shape (a clock, an HTTP client, an uploader) is typed as a `Protocol`, so fakes
need no inheritance. *Why:* [Hynek, "Subclassing in Python Redux"](https://hynek.me/articles/python-subclassing-redux/).
*Check:* review.

**TYP-7 SHOULD.** Use `Literal` for small closed sets of config values, and `StrEnum` when code iterates over the set
or attaches behaviour to it.

**TYP-8 SHOULD.** Avoid `Any` outside JSON-shaped payloads and lazily imported third-party objects. Use `object` for
"accepts anything".

**TYP-9 MUST.** Dicts are for wire payloads only (JSON in, JSON out). A dict with a fixed set of known keys is a class.
*Check:* review.

## 7. Code style (STY)

**STY-1 MUST.** Format with ruff format: 88 columns, double quotes. *Why:* the ecosystem default, the most readable
side by side, and inside the accessibility limit Black documents
([Black](https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html)). *Check:*
`ruff format --check`.

**STY-2 MUST.** Lint with the template's curated rule set:
`E F W I B UP SIM RET PTH C4 RUF TID FBT N PERF G LOG BLE PL D NPY ERA T20 C90` (plus `FA` below 3.14). `D401` is
selected explicitly, because the google docstring convention silently drops it. Ignored on purpose: `PLR2004`,
`PLR0913`, `PLC0415`, `D102`, `D103`, `D105`, `D106`, `D107`. The set changes only by changing
this guide. A `# noqa` names the rule and gives a reason. *Why:* an explicit select keeps upgrades from changing the
rules silently ([ruff](https://docs.astral.sh/ruff/linter/)). *Check:* `ruff check`.

**STY-3 MUST.** Imports are absolute, and `nuikit` imports form their own block between third-party and project
imports. *Check:* ruff TID252 with `ban-relative-imports = "all"`; a `nuikit` isort section.

**STY-4 MUST.** Every optional parameter and every boolean parameter is keyword-only (after `*`). Only the one or two
obvious subjects of a call are positional. *Check:* ruff FBT for booleans; review for the rest.

**STY-5 MUST.** Naming:

- Modules are short nouns (`harness`, `soundness`). Functions are verbs (`select`, `bind`).
- Classes are nouns, and family items carry the family suffix (`LiteLLMEndpoint`, `GoldPatches`).
- Schemas end in `Config`. Acronyms stay capitalised (`HDBSCANClustering`, `BQ2GCSCollector`).
- Constants are UPPER_SNAKE right after the imports.
- Anything not used outside its module starts with `_`.

*Check:* ruff N; review.

**STY-6 MUST.** A name holding a number with a unit ends in a short unit suffix: `_s`, `_ms`, `_mb`, `_gb`,
`_tokens`, `_steps`. Minutes and hours are spelled out (`_minutes`, `_hours`), because `_min` reads as "minimum".
A name that mirrors an external format (a file another tool reads, a library's parameters, a CLI flag) keeps that
format's spelling: `timeout_seconds` in a scorer's config file, `max_model_len` from vLLM. *Check:* review.

**STY-7 MUST.** Use pathlib, never `os.path`. *Check:* ruff PTH.

**STY-8 MUST.** `.py` files are ASCII: use `;`, `:`, `-` and `->`, never em dashes or Unicode arrows. Markdown may use
any typography. Under **[uni]**, user-facing strings may be Ukrainian (UNI-4). *Why:* greppable and terminal-safe.
*Check:* a pre-commit non-ASCII hook in `rnd`.

**STY-9 SHOULD.** Prefer early returns to nesting, comprehensions to `map`/`filter`, and `match` for dispatch on a
shape or a file suffix.

**STY-10 SHOULD.** Keep within the complexity budget (C901 at 10, pylint's branch and statement limits). Split long
functions at real seams, not into one-call helpers that are shallow modules
([Ousterhout](https://github.com/johnousterhout/aposd-vs-clean-code)). *Check:* ruff C901, PLR0912, PLR0915.

## 8. Comments and docstrings (DOC)

**DOC-1 MUST.** Every module starts with a one-line docstring stating its single responsibility. A CLI module's or
script's docstring is its `--help` text and may add a usage block. *Why:* "what is this file for" stays answerable and
greppable, and keeps each module honest about its scope ([PEP 257](https://peps.python.org/pep-0257/)).
*Check:* ruff D100, D104.

**DOC-2 MUST.** Docstrings are one line where possible:

- a function's is imperative ("Return the run directory for `name`."); `D401` checks this;
- a class's is a noun phrase saying what an instance represents ("Spacing between requests to one upstream.");
- every public class has one (`D101`);
- a function or method gets one when its name and signature don't already say it all.

*Check:* ruff D101, D401; `check-comments` flags a class docstring that opens with an order; review.

**DOC-3 SHOULD.** Add Google-style `Args:`, `Returns:` or `Raises:` sections only for what types can't express: units,
shapes, valid ranges, what `None` or an empty value means, and errors that are part of the contract.

**DOC-4 MUST.** A comment explains what the code can't say:

- an external constraint;
- a non-obvious reason;
- a unit;
- where a value came from (cite the source);
- what `None` means.

Never restate the code, never use section banners, and never leave commented-out code.
*Why:* "Comments that contradict the code are worse than no comments" ([PEP 8](https://peps.python.org/pep-0008/)).
Information that code can't express still needs writing down ([Ousterhout](https://github.com/johnousterhout/aposd-vs-clean-code)).
*Check:* ruff ERA001; `check-comments` flags banners; `review-comments` asks Claude whether new comments say anything
the code doesn't (a Claude Code `Stop` hook, and on demand with `pre-commit run review-comments --hook-stage manual`).

```python
# Bad: restates the code.
# Perform clustering
labels = model.fit_predict(embeddings)

# Good: says what the code can't.
# Wildcard is mandatory: BigQuery extract rejects single-file URIs for tables over 1 GB.
uri = f"{workdir_uri}/part-*.parquet"
```

**DOC-5 MUST.** Comments are sentences: capitalised and ending with a period. A sentence that opens with a
lowercase name puts it in backticks (`` `git` is not installed. ``). *Check:* `check-comments`, in pre-commit and as a
Claude Code `PostToolUse` hook on every edited `.py` file.

**DOC-6 SHOULD.** A `TODO` says why it isn't done now. Code generated without review is marked as such until reviewed.
*Check:* ruff TD004 to TD007 (a `TODO:` with a description); review for the why.

**DOC-7 MUST.** YAML comments document user-facing settings. Generated YAML carries the `Field` descriptions (CFG-3).

## 9. Errors (ERR)

**ERR-1 MUST.** A problem the user can fix raises `nuikit.errors.UserError` or a subclass; a package that needs its own
family of errors subclasses it (`ProxyError(UserError)`).
Each carries an `exit_code`: `ConfigError` exits with 2 and `DataError` with 3. Every other exception is a bug and keeps
its traceback. *Why:* "a bug is a kind of error the programmer didn't expect"; recoverable errors are expected
([Duffy](https://joeduffyblog.com/2016/02/07/the-error-model/)). This is the model click's `ClickException` uses.
*Check:* `nuikit` error tests.

**ERR-2 MUST.** Each entry point has one boundary, `@cli_boundary`. It turns package errors, pydantic
`ValidationError` and OmegaConf errors into `error: <message>` on stderr and the matching exit code. Nothing else
catches broadly. *Check:* review.

**ERR-3 MUST.** A message is lowercase with no trailing period. It states what is wrong, then `; ` and the remedy,
naming the command or config key. An unknown name lists the valid ones.

```text
error: no soundness data; run `g4swe-grade controls` first
error: unknown endpoint kind 'gemni'; registered: gemini, litellm, passthrough
```

*Check:* review.

**ERR-4 MUST.** Fail fast at the edge: check that paths exist, kinds are registered and credentials work (a one-token
ping) before any expensive work starts. *Why:* [Shore, "Fail Fast"](https://www.martinfowler.com/ieeeSoftware/failFast.pdf).
*Check:* review.

**ERR-5 MUST.** Translating an exception uses `raise ... from err`. A broad `except Exception` exists only at an
isolation point, such as a callback that must not stop training or a best-effort notification, and its `noqa` says
why. *Check:* ruff B904, BLE001.

**ERR-6 MAY.** Messages are written at the raise site. Ruff's TRY003 and EM rules, which want them inside the class,
are not selected.

## 10. Logging (LOG)

**LOG-1 MUST.** Logging is structlog over the standard library. Each module that logs has
`log = structlog.stdlib.get_logger()` at the top (typed, unlike `structlog.get_logger()`). `nuikit.logging.configure_logging()` is called once, by the entry point; no
other code configures logging. *Why:* one pipeline for our events and for third-party stdlib logs (LiteLLM, httpx,
Hydra) ([structlog](https://www.structlog.org/en/stable/standard-library.html)). *Check:* template.

**LOG-2 MUST.** Events are stable snake_case ids with key-value context: `log.info("proxy_started", port=8000)`. Never
build an event with an f-string or `%`. *Why:* events stay queryable in JSON logs and in BigQuery. *Check:* review.

**LOG-3 MUST.** The renderer is pretty console output when stderr is a TTY and JSON otherwise. Hydra's `job_logging`
and `hydra_logging` are disabled. *Check:* template.

**LOG-4 MUST.** Logs record events. Output meant for the user (tables, results) goes to stdout through `click.echo` or
rich, never through the logger. Library code never calls `print`. *Check:* ruff T201, allowed only in `cli/` and
`scripts/`.

**LOG-5 SHOULD.** Bind run context once with `structlog.contextvars.bind_contextvars(run=...)` instead of repeating it
in every event.

## 11. Tests (TST)

**TST-1 MUST.** Tests are pytest functions (no test classes) named as sentences stating a behaviour:
`test_sound_selection_never_falls_back_to_every_task`. *Check:* review.

**TST-2 MUST.** Unit tests come first. Each case covers a distinct branch or behaviour: no cross-product
parametrisation, and nothing re-tested at a higher level that a unit test already covers.
*Why:* test behaviour, one test per behaviour ([SWE at Google ch. 12](https://abseil.io/resources/swe-book/html/ch12.html)).
*Check:* review.

**TST-3 MUST.** Test doubles are in-process fakes (`ScriptedEndpoint`, `httpx.MockTransport`), `tmp_path` and
`monkeypatch`. `unittest.mock` is banned. Fakes live in `tests/conftest.py` or `tests/fakes.py`; a fake with logic has
its own tests. *Why:* prefer real objects, then fakes; interaction testing couples tests to the implementation
([SWE at Google ch. 13](https://abseil.io/resources/swe-book/html/ch13.html),
[Fowler](https://martinfowler.com/articles/mocksArentStubs.html)). *Check:* ruff `banned-api`.

**TST-4 MUST.** The layout mirrors `src/` module by module: `tests/<pkg>/<sub>/test_<module>.py` for every module
with branching logic. Exempt modules are those with nothing a unit test could distinguish: schemas whose rules
pydantic enforces, error classes, re-exporting `__init__` files, and thin wrappers that only start an external
process (a `docker build`). They are covered by the invariants or the integration test. Cross-cutting
invariants live in `tests/test_invariants.py`. End-to-end tests live in `tests/integration/`, are marked
`integration` and are deselected by default (`-m integration` runs them). *Check:* `--strict-markers`; review.

**TST-5 MUST.** The invariant tests check that:

- every entry config composes and validates;
- generated configs are fresh;
- the import contracts hold;
- every registered kind builds from its generated YAML.

*Check:* the template's `tests/test_invariants.py`.

**TST-6 MUST.** Child processes, servers and Docker appear only in tests of what can't be measured in process. Before
adding a slow test, check `pytest --durations=10`. The unit suite stays under about 10 s. *Check:* review.

**TST-7 SHOULD.** Separate arrange, act and assert with blank lines. Compare related values in one tuple assert. A test
module's docstring states the invariant it protects.

**TST-8 SHOULD.** Test ML code with tiny real models, not mocks: loss decreases, and a batch can be overfitted
([Yan](https://eugeneyan.com/writing/unit-testing-ml/)).

## 12. Runs, reproducibility and notebooks (RUN)

**RUN-1 MUST.** Every run writes `runs/<run_name>/` containing:

- `config.yaml`: resolved, with secrets masked;
- `run.json`: git SHA, dirty flag, argv and start time;
- the run's outputs.

Hydra writes nothing else. *Why:* any result can be traced back to its code and config. *Check:* `nuikit` runs tests.

**RUN-2 MUST.** Seed once in the entry point with `seed_everything(cfg.seed)`. Code that needs randomness takes an
explicit `np.random.Generator` or `torch.Generator`. Never call the global `np.random.*` functions.
*Why:* "global state is always problematic" ([NEP 19](https://numpy.org/neps/nep-0019-rng-policy.html)); full
determinism also needs PyTorch's flags ([PyTorch](https://docs.pytorch.org/docs/stable/notes/randomness.html)).
*Check:* ruff NPY002.

**RUN-3 MUST.** Pin what can't be seeded:

- Hugging Face model revisions (commit SHA);
- dataset revisions;
- Docker image digests;
- `uv.lock`.

*Check:* review; a test that rejects unpinned model configs where models are configured.

**RUN-4 MAY [rnd].** Setting `tracker: wandb` mirrors a run to Weights & Biases. The run directory stays the source of
truth.

**RUN-5 MUST.** Notebooks are for exploration: `notebooks/NN-topic.ipynb`, outputs stripped, never imported. Logic
worth reusing moves into `src/` with a test. Third-party notebooks go in `notebooks/reference/`. *Why:* "notebooks are
for exploration and communication, source files are for repetition"
([Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/opinions/)). *Check:* nbstripout
pre-commit hook.

**RUN-6 MUST.** Raw data is immutable and gitignored. Downloads are idempotent (write a `.part` file, then rename) and
verified by size or SHA. *Check:* review.

**RUN-7 SHOULD.** The storage format follows the data's role:

- CSV for raw data as received;
- parquet for derived tables;
- JSON for metrics (`ensure_ascii=False, indent=2`);
- NPZ for arrays.

## 13. Repository docs (RDOC)

**RDOC-1 MUST.** README.md is the user's and operator's view: setup, daily workflow, commands, outputs, caveats.
CONTRIBUTING.md is the contributor's view: architecture, layout, families, configs, deviations, the "Extending" table,
tests and commits. *Why:* one document, one purpose ([SWE at Google ch. 10](https://abseil.io/resources/swe-book/html/ch10.html)).
*Check:* template skeletons.

**RDOC-2 MUST.** A standalone subpackage has its own README.md and CONTRIBUTING.md next to its code. *Check:* review.

**RDOC-3 MUST.** Diagrams are mermaid. Flowcharts colour pure components with `classDef pure` and effectful ones with
`classDef side`, using the template's palette. The main run gets one sequence diagram. *Check:* template.

**RDOC-4 MUST.** AGENTS.md is the entry point for coding agents, at most 150 lines: commands, layout, the top MUSTs,
and pointers to CONTRIBUTING and this guide. CLAUDE.md contains `@AGENTS.md` plus any Claude-only extras. Agent files
point to this guide instead of copying it, and leave to linters what linters check. *Why:*
[agents.md](https://agents.md/); [Claude Code memory](https://code.claude.com/docs/en/memory) recommends short,
specific files. Each project also carries `CONVENTIONS.md`, a read-only copy of this guide rendered by the
template, and a `conventions-reviewer` subagent (`.claude/agents/`) that checks a branch or the whole repo against
it. *Check:* template.

**RDOC-5 MUST.** Docs change in the same commit as the code they describe. A stale doc is a bug. *Check:* review.

## 14. Git (GIT)

**GIT-1 MUST.** Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

- a standard type: `feat fix docs refactor test build ci perf style chore revert`;
- an optional scope;
- a lowercase imperative subject, with no period, of at most 72 characters;
- no articles (`a`, `an`, `the`) and no filler: say what changed in as few words as hold it.

Example: `fix(proxy): retry on 429 from upstream`, not `fix(proxy): add a retry for the 429 errors`. *Why:* the default tooling accepts exactly these types, and the
imperative matches git's own convention ([Beams](https://cbea.ms/git-commit/)). *Check:* the
`conventional-pre-commit` and `check-commit-msg` commit-msg hooks.

**GIT-2 MUST.** A commit message is one line: no body and no trailers. A reason worth keeping goes where readers
look for it: a code comment for a constraint, the PR description for an alternative that was rejected. Claude Code's
own trailer is off in `.claude/settings.json` (`attribution`). *Check:* `check-commit-msg`.

**GIT-3 MUST.** Branches are short-lived and named `<type>/<slug>` (`feat/`, `fix/`, `docs/`, `refactor/`, plus `exp/`
for experiments). Merges are squash-merges, and the PR title is the conventional commit that lands on `main`.
`make github` sets the repo up once: squash-merge only, the PR title as the commit title with an empty body (GIT-2),
merged branches deleted. GitHub appends ` (#N)` to the title, so PR titles stay within 65 characters.
*Check:* `make github`; review.

**GIT-4** Retired on 2026-10-19: commit messages are one line, without trailers (GIT-2).

**GIT-5 MUST.** Secrets, data, run outputs and notebook outputs are never committed. *Check:* gitleaks, nbstripout,
`.gitignore`.

**GIT-6 MUST.** A PR description follows `.github/pull_request_template.md`: a summary of why, the changes made
with the alternatives rejected, and the checklist; results, how to reproduce them and notes for the reviewer when
they apply. *Why:* commits are one line, so the PR holds the reasoning, and the
squash commit links to it by number. *Check:* template; review.

## 15. Tooling (TOOL)

**TOOL-1 MUST.** `make check` runs ruff check, ruff format `--check`, pyright, `lint-imports` and pytest, and CI runs
it on every pull request. pre-commit runs the fast checks plus the commit-msg lint, nbstripout, gitleaks and the
`uv lock` check. *Why:* rules that a tool can check are enforced by a tool
([SWE at Google ch. 8](https://abseil.io/resources/swe-book/html/ch08.html)). *Check:* template.

**TOOL-2 MUST.** Tool versions come from `uv.lock`. Hooks for Python tools are local `uv run` hooks, so pre-commit, CI
and editors all use the same versions. *Check:* template.

**TOOL-4 MUST.** The checks this guide adds on top of ruff live in the conventions repo as the `conventions-hooks`
package (`check-comments`, `review-comments`), a dev dependency of every project, pinned by `uv.lock`. They run in two
layers with the same code: pre-commit gates every commit by anyone, and `.claude/settings.json` hooks give Claude the
findings while it works (`PostToolUse` after each edit, `Stop` before it hands back). *Why:* only pre-commit sees every
author, but feedback during the edit is cheaper than at commit time. *Check:* template.

**TOOL-3 MUST.** A generated project keeps its `.copier-answers.yml` and pulls template changes with `copier update`.
*Check:* review.

**TOOL-5 MUST.** Files nobody edits by hand are listed in `.gitattributes` with `protected=<why>`:

- `generated`: config mirrors, `report/generated/`, `.copier-answers.yml`;
- `vendored`: `src/nuikit/`, `tests/nuikit/`, `CONVENTIONS.md`, the reviewer subagent;
- `published`: third-party files kept as published, such as `notebooks/reference/`.

The same lines carry `linguist-generated` or `linguist-vendored`, so GitHub folds those diffs in pull requests. The
`check-protected` Claude Code `PreToolUse` hook refuses edits to them with the reason and the right place to make the
change; the commands that own them (`make configs`, `copier update`) still write them. The hook fails open: a broken
environment lets edits through instead of blocking every one. Names carry no marker (no `_`
prefix): `_` means private in Python, and `nuikit` is imported everywhere. *Why:* agents fix whatever file is in
front of them, and a refusal that names the source is the cheapest redirect. *Check:* template; `check-protected PATH`.

## 16. uni profile (UNI)

**UNI-1 MUST.** A course repo is a uv workspace:

- The root holds the shared course package `src/<course>/` (paths, labs, storage, report macros, LaTeX) next to
  `src/nuikit/` (LAY-2).
- Each lab is a member at `labs/NNN-topic/` with package `labNNN` and `dependencies = []`; shared dependencies live
  at the root.
- New labs are created only with `make lab`.

*Why:* duplicated helpers across labs were the main problem in the first course repo. *Check:* template.

**UNI-2 MUST.** The deliverable is scripts plus generated LaTeX. Hydra scripts write the data, the figures and a
`values.tex` of macros. `report.tex` never contains a typed number. A Dockerised XeLaTeX build makes the PDF
(`make report LAB=NNN`). *Check:* review.

**UNI-3 MUST.** A lab's parameters come from its `config/`, never from constants in code. *Check:* review.

**UNI-4 MAY.** User-facing text (reports, plot labels, messages for graders) may be in Ukrainian. Identifiers, comments
and docstrings are in English.

**UNI-5 SHOULD.** Commit only raw data; everything else regenerates byte for byte. Tests check invariants (shapes,
monotonicity, conservation), never values copied from config. Each script gets a subprocess smoke test on a tiny config.

**UNI-6 MUST.** Branches are `lab/NNN-topic`, and they squash-merge as `feat(labNNN): <title>`. *Check:* the commit-msg
hook.

## Decisions

Contested choices, what was weighed and why this guide picks what it does. Revisit an entry when its reason no longer
holds.

| topic | decision | alternatives | why |
|---|---|---|---|
| line length | 88 | 79 (PEP 8, Google), 100, 120 (earlier repos) | ecosystem default; no primary guide endorses 120 |
| multi-part repos | one package with subpackages | uv workspace; several top-level modules | simplest, no name clashes; import-linter keeps the boundaries |
| shared building blocks | vendored by the template | personal library; copying by hand | no runtime dependency on a personal package in employer repos; `copier update` spreads fixes |
| their layout | second top-level package `nuikit` | `<pkg>/framework/` + `<pkg>/runtime/`; one `core/` folder; `packages/kit/` workspace member | project code reads without template plumbing; one `src/`, one distribution, no workspace |
| implementation lookup | registry with auto-discovery | explicit imports; lazy map; discriminated union | adding a file is all it takes; costs accepted at this scale (FAM) |
| config bridge | `Schema.from_hydra` | `_target_` + instantiate; Hydra structured configs | parse at the boundary; YAML never names classes |
| config defaults | schema is the source, YAML generated | YAML + schema + parity test; YAML only | one source of truth while YAML stays readable |
| entry configs | hand-written, composing a generated mirror | generated entry config; hand-written only | one place to edit the standard run while every default stays documented |
| CLI | Hydra for config-heavy commands, click for utilities | Hydra only; click wrapping Hydra; typer | each fits its job |
| entry points | interface commands in `cli/`, one-offs in `scripts/` | `scripts/` for everything; `cli/` only | commands get in-process tests and the layer check; one-offs stay out of the package |
| data classes | attrs for every class, pydantic for configs | dataclasses; pydantic everywhere | validation at the edge, plain typed state inside; no `__init__` boilerplate |
| interfaces | ABC families, Protocol seams | ABC only; Protocol only | registries need nominal bases; fakes need none |
| type checker | pyright standard, strict on `nuikit` | mypy --strict; basedpyright; ty (beta) | checks unannotated code; understands attrs and pydantic natively |
| `__future__` annotations | always below 3.14, never from 3.14 | never; only where needed | consistent and automatic; follows PEP 649/749 |
| module docstrings | one line on every module | only `__init__` and CLI (earlier rule) | each module states its responsibility (PEP 257, Google) |
| errors | base error with exit codes | single UserError; builtins only | scripts can tell config errors from data errors |
| logging | structlog over stdlib, snake_case events | stdlib %-style; loguru | structured events for cloud pipelines; one renderer for third-party logs |
| test doubles | fakes, mocks banned | mocks at unmanaged edges (Khorikov) | tests don't couple to the implementation (SWE at Google ch. 13) |
| commits | standard types, imperative, one line, no articles | custom `doc`/`ref`; behaviour-as-fact subjects; bodies with the why | default tooling accepts them; git convention; terse history you can scan |
| merging | squash | rebase-merge; commit to main | messy branch history is fine; `main` stays one commit per change |
| Python | latest stable | 3.12 floor | newest language features; pin lower per project when forced |

## Sources

- Style: [PEP 8](https://peps.python.org/pep-0008/), [PEP 257](https://peps.python.org/pep-0257/),
  [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html),
  [Black code style](https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html),
  [ruff linter docs](https://docs.astral.sh/ruff/linter/).
- Design:
  - Parnas, [On the criteria to be used in decomposing systems into modules](https://blog.acolyer.org/2016/09/05/on-the-criteria-to-be-used-in-decomposing-systems-into-modules/) (1972)
  - [Ousterhout vs Martin](https://github.com/johnousterhout/aposd-vs-clean-code) (2025)
  - [Cosmic Python](https://www.cosmicpython.com/book/) (2020)
  - Fowler, [Presentation Domain Data Layering](https://martinfowler.com/bliki/PresentationDomainDataLayering.html)
  - Brown, [Modular monolith](https://simonbrown.je/modular-monolith)
  - Bernhardt, [Functional core, imperative shell](https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell)
  - Metz, [The Wrong Abstraction](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)
  - Wu, [Registration Does Not Scale Well](https://ppwwyyxx.com/blog/2023/Registration-Does-Not-Scale-Well/)
- Types and data:
  - [Hynek, Subclassing in Python Redux](https://hynek.me/articles/python-subclassing-redux/)
  - [attrs: Why not…](https://www.attrs.org/en/stable/why.html)
  - [Hynek, Design Pressure](https://speakerdeck.com/hynek/design-pressure)
  - King, [Parse, don't validate](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/)
  - PEPs [649](https://peps.python.org/pep-0649/), [749](https://peps.python.org/pep-0749/), [810](https://peps.python.org/pep-0810/)
- Errors and logging:
  - Shore, [Fail Fast](https://www.martinfowler.com/ieeeSoftware/failFast.pdf)
  - Duffy, [The Error Model](https://joeduffyblog.com/2016/02/07/the-error-model/)
  - [Logging HOWTO](https://docs.python.org/3/howto/logging.html)
  - [structlog and the standard library](https://www.structlog.org/en/stable/standard-library.html)
- Tests: [SWE at Google](https://abseil.io/resources/swe-book) ch. 11–14,
  Fowler, [Mocks Aren't Stubs](https://martinfowler.com/articles/mocksArentStubs.html),
  Yan, [Don't mock ML models](https://eugeneyan.com/writing/unit-testing-ml/).
- ML and research code:
  - Sculley et al., [Hidden Technical Debt in ML Systems](https://papers.nips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html) (2015)
  - Wilson et al., [Best Practices for Scientific Computing](https://doi.org/10.1371/journal.pbio.1001745) (2014)
  - Wilson et al., [Good enough practices](https://doi.org/10.1371/journal.pcbi.1005510) (2017)
  - [Cookiecutter Data Science opinions](https://cookiecutter-data-science.drivendata.org/opinions/)
  - [NEP 19](https://numpy.org/neps/nep-0019-rng-policy.html)
  - [PyTorch reproducibility](https://docs.pytorch.org/docs/stable/notes/randomness.html)
- Layout and tools:
  - [Hynek, Testing & Packaging](https://hynek.me/articles/testing-packaging/)
  - [pytest good practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
  - [uv build backend](https://docs.astral.sh/uv/concepts/build-backend/)
  - [import-linter](https://import-linter.readthedocs.io/en/stable/)
  - [copier](https://copier.readthedocs.io/)
- Process:
  - [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/)
  - Beams, [How to Write a Git Commit Message](https://cbea.ms/git-commit/)
  - [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)
  - [agents.md](https://agents.md/)
  - [Claude Code memory](https://code.claude.com/docs/en/memory)

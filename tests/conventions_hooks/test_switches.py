"""Switches on a variant name are reported where they repeat or grow too long."""

from __future__ import annotations

import ast

import pytest

from conventions_hooks import switches


def found(
    source: str, *, waived: frozenset[int] = frozenset()
) -> list[tuple[int, str]]:
    findings = switches.check(ast.parse(source), "src/demo/runner.py", waived=waived)
    return [(f.line, f.rule) for f in findings]


SHOTGUN = """
def start(cfg):
    if cfg.backend == "modal":
        launch_modal()
    elif cfg.backend == "local":
        launch_local()


def cost(cfg):
    if cfg.backend == "modal":
        return price_modal()
    return 0.0
"""

LONG_CHAIN = """
def score(pred, gold, *, metric):
    if metric == "f1":
        return f1(pred, gold)
    elif metric == "em":
        return exact(pred, gold)
    elif metric == "bleu":
        return bleu(pred, gold)
    raise UnknownMetricError(metric)
"""

GUARDS = """
def render(rows, *, fmt):
    if fmt == "csv":
        return to_csv(rows)
    if fmt == "json":
        return to_json(rows)
    if fmt == "md":
        return to_markdown(rows)
    raise UnknownFormatError(fmt)
"""

CONSTANTS = """
def fraction(split):
    match split:
        case "train":
            return 0.8
        case "val":
            return 0.1
        case "test":
            return 0.1
"""

# The "Bad" example of ARC-9 in the guide.
CONDITIONAL = """
def start(cfg: RunConfig) -> None:
    if cfg.backend == "modal":
        ...
    elif cfg.backend == "local":
        ...


def cost_usd(cfg: RunConfig) -> float:
    return 0.3 if cfg.backend == "modal" else 0.0
"""

CONDITIONALS = """
def label(mode):
    return "T" if mode == "train" else "E"


def steps(mode):
    return (
        100
        if mode in ("train", "tune")
        else 10
    )
"""

# A conditional expression above does not hide that `teardown` repeats `setup`.
BELOW_A_CONDITIONAL = """
def label(cfg):
    return "GPU" if cfg.device == "cuda" else "CPU"


def setup(cfg):
    if cfg.device == "cpu":
        pin()


def teardown(cfg):
    if cfg.device == "cpu":
        unpin()
"""

# Walked in the order of the source, `stop` meets "drop" first, so `halt` repeats it.
NESTED_FIRST = """
def stop(mode, items):
    for item in items:
        for part in item:
            if mode == "drop":
                drop(part)
    while items:
        if mode == "pop":
            items.pop()


def halt(mode):
    if mode == "drop":
        leave()
"""

# The same below the first level: the two loops are children of one `for`.
NESTED_SIBLINGS = """
def stop(mode, items):
    for item in items:
        while item:
            if mode == "drop":
                drop(item)
        while items:
            if mode == "pop":
                items.pop()


def halt(mode):
    if mode == "drop":
        leave()
"""

# One test in each of two functions is the second function the rule forbids.
LONE_PAIR = """
def start(cfg):
    if cfg.backend == "modal":
        launch_modal()


def stop(cfg):
    if cfg.backend == "modal":
        halt_modal()
"""

KIND_CHAIN = """
def run(kind):
    if kind == "api":
        call_api()
    elif kind == "local":
        call_local()
    elif kind == "batch":
        call_batch()
"""

KIND_MATCH = """
def cost(kind, item):
    match kind:
        case "api":
            return price_api(item)
        case "local":
            return 0.0
        case "batch":
            return price_batch(item)
"""

# Only the `type` of a `device` is another library's name.
SCHEDULER_TYPE = """
def warmup(cfg):
    if cfg.scheduler.type == "cosine":
        return ramp(cfg)


def decay(cfg):
    if cfg.scheduler.type == "cosine":
        return anneal(cfg)
"""

PLAIN_DEVICE = """
def pin(device):
    if device == "cuda":
        return True
    return False


def sync(device):
    if device == "cuda":
        wait()
"""

BUILT_THEN_CONFIGURED = """
def build(backend, cfg):
    if backend == "modal":
        runner = ModalRunner(cfg)
        runner.warm_up()
    elif backend == "local":
        runner = LocalRunner(cfg)
    elif backend == "slurm":
        runner = SlurmRunner(cfg)
    return runner
"""

ASSIGNED_TO_TWO_NAMES = """
def build(backend, cfg):
    if backend == "modal":
        runner = ModalRunner(cfg)
    elif backend == "local":
        pool = LocalPool(cfg)
    elif backend == "slurm":
        runner = SlurmRunner(cfg)
"""

RETURNED_AND_ASSIGNED = """
def build(backend, cfg):
    if backend == "modal":
        return ModalRunner(cfg)
    elif backend == "local":
        runner = LocalRunner(cfg)
    elif backend == "slurm":
        return SlurmRunner(cfg)
    return runner
"""

LOGGED_THEN_BUILT = """
def build(backend, cfg):
    if backend == "modal":
        log.info("backend_chosen")
        return ModalRunner(cfg)
    if backend == "local":
        return LocalRunner(cfg)
    if backend == "slurm":
        return SlurmRunner(cfg)
"""

# A test on a string that does not read as a name is no arm; the arms around it count.
EMPTY_FIRST = """
def run(mode):
    if mode == "":
        default()
    elif mode == "train":
        train()
    elif mode == "eval":
        evaluate()
    elif mode == "export":
        export()
"""

EMPTY_FIRST_IN_A_MATCH = """
def run(mode):
    match mode:
        case "":
            default()
        case "train":
            train()
        case "eval":
            evaluate()
        case "export":
            export()
"""

EMPTY_LAST = """
def run(mode):
    if mode == "train":
        train()
    elif mode == "eval":
        evaluate()
    elif mode == "export":
        export()
    elif mode == "":
        default()
"""

EMPTY_FIRST_THEN_REPEATED = """
def run(mode):
    if mode == "":
        default()
    elif mode == "train":
        train()
    elif mode == "eval":
        evaluate()


def cost(mode):
    if mode == "train":
        return 1.0
    return 0.0
"""

# A run of guard clauses is reported at the first of them that has an arm.
EMPTY_GUARD_FIRST = """
def render(rows, *, fmt):
    if fmt == "":
        return to_text(rows)
    if fmt == "csv":
        return to_csv(rows)
    if fmt == "json":
        return to_json(rows)
    if fmt == "md":
        return to_markdown(rows)
    raise UnknownFormatError(fmt)
"""

EMPTY_GUARD_BETWEEN = """
def render(rows, *, fmt):
    if fmt == "csv":
        return to_csv(rows)
    if fmt in ("", "-"):
        return to_text(rows)
    if fmt == "json":
        return to_json(rows)
    if fmt == "md":
        return to_markdown(rows)
    raise UnknownFormatError(fmt)
"""

# A membership test on strings that are no names keeps the chain going.
MEMBERSHIP_ON_NON_NAMES_FIRST = """
def run(mode):
    if mode in ("", None):
        default()
    elif mode == "train":
        train()
    elif mode == "eval":
        evaluate()
    elif mode == "export":
        export()
"""

# The expression on an empty string is no switch: `first` is the one `second` repeats.
EMPTY_CONDITIONAL_FIRST = """
def label(mode):
    return "none" if mode == "" else mode


def first(mode):
    return 1 if mode == "train" else 0


def second(mode):
    return 2 if mode == "train" else 0
"""

# The factory is never reported, but a function on one of its values is, wherever it is.
FACTORY_THEN_COST = """
def build(cfg):
    if cfg.backend == "modal":
        return Modal()
    elif cfg.backend == "local":
        return Local()


def cost(cfg):
    if cfg.backend == "modal":
        return bill()
    return 0.0
"""

COST_THEN_FACTORY = """
def cost(cfg):
    if cfg.backend == "modal":
        return bill()
    return 0.0


def build(cfg):
    if cfg.backend == "modal":
        return Modal()
    elif cfg.backend == "local":
        return Local()
"""

FACTORY_AS_CONDITIONAL = """
def build(cfg):
    return Modal() if cfg.backend == "modal" else Local()


def cost(cfg):
    if cfg.backend == "modal":
        return bill()
"""

# A short switch is compared with a long chain below it, as with one above it.
ABOVE_A_CHAIN = """
def label(cfg):
    if cfg.backend == "modal":
        return "cloud"
    return "home"


def start(cfg):
    if cfg.backend == "modal":
        launch_modal()
    elif cfg.backend == "local":
        launch_local()
    elif cfg.backend == "slurm":
        launch_slurm()
"""

# `cost` repeats `start`, though `submit` came first on `backend`.
THIRD_FIRST = """
def submit(cfg):
    if cfg.backend == "slurm":
        queue()


def start(cfg):
    if cfg.backend == "modal":
        launch()


def cost(cfg):
    if cfg.backend == "modal":
        return bill()
    return 0.0
"""

# A leading underscore marks a function as private, not as a class.
PRIVATE_FUNCTIONS = """
def build(backend):
    if backend == "modal":
        return _modal()
    if backend == "local":
        return _local()
    if backend == "slurm":
        return _slurm()
    raise UnknownBackendError(backend)
"""

# The name of a model in a config is the project's own variant name.
MODEL_NAME = """
def load(cfg):
    if cfg.model.name == "llama":
        return load_llama(cfg)
    if cfg.model.name == "qwen":
        return load_qwen(cfg)
    if cfg.model.name == "gemma":
        return load_gemma(cfg)
    raise UnknownModelError(cfg.model.name)
"""


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (SHOTGUN, [(10, "ARC-9")]),
        (LONG_CHAIN, [(3, "ARC-9")]),
        (GUARDS, [(3, "ARC-9")]),
        (CONSTANTS, [(3, "ARC-9")]),
        (CONDITIONAL, [(10, "ARC-9")]),
        (CONDITIONALS, [(9, "ARC-9")]),
        (BELOW_A_CONDITIONAL, [(12, "ARC-9")]),
        (NESTED_FIRST, [(13, "ARC-9")]),
        (NESTED_SIBLINGS, [(13, "ARC-9")]),
        (LONE_PAIR, [(8, "ARC-9")]),
        (KIND_CHAIN, [(3, "ARC-9")]),
        (KIND_MATCH, [(3, "ARC-9")]),
        (SCHEDULER_TYPE, [(8, "ARC-9")]),
        (PLAIN_DEVICE, [(9, "ARC-9")]),
        (BUILT_THEN_CONFIGURED, [(3, "ARC-9")]),
        (ASSIGNED_TO_TWO_NAMES, [(3, "ARC-9")]),
        (RETURNED_AND_ASSIGNED, [(3, "ARC-9")]),
        (LOGGED_THEN_BUILT, [(3, "ARC-9")]),
        (EMPTY_FIRST, [(3, "ARC-9")]),
        (EMPTY_FIRST_IN_A_MATCH, [(3, "ARC-9")]),
        (EMPTY_LAST, [(3, "ARC-9")]),
        (EMPTY_FIRST_THEN_REPEATED, [(12, "ARC-9")]),
        (EMPTY_GUARD_FIRST, [(5, "ARC-9")]),
        (EMPTY_GUARD_BETWEEN, [(3, "ARC-9")]),
        (EMPTY_CONDITIONAL_FIRST, [(11, "ARC-9")]),
        (MEMBERSHIP_ON_NON_NAMES_FIRST, [(3, "ARC-9")]),
        (FACTORY_THEN_COST, [(10, "ARC-9")]),
        (COST_THEN_FACTORY, [(3, "ARC-9")]),
        (FACTORY_AS_CONDITIONAL, [(7, "ARC-9")]),
        (ABOVE_A_CHAIN, [(9, "ARC-9"), (3, "ARC-9")]),
        (THIRD_FIRST, [(13, "ARC-9")]),
        (PRIVATE_FUNCTIONS, [(3, "ARC-9")]),
        (MODEL_NAME, [(3, "ARC-9")]),
    ],
    ids=[
        "same-variant-in-two-functions",
        "three-arms-run-code",
        "three-guard-clauses",
        "three-arms-map-constants",
        "conditional-expression-repeats-a-chain",
        "two-conditional-expressions",
        "statements-below-a-conditional-expression",
        "nested-switch-met-first",
        "nested-siblings-in-source-order",
        "one-test-in-each-of-two-functions",
        "three-arms-on-a-name-kind",
        "match-on-a-name-kind",
        "type-of-something-else",
        "plain-name-device",
        "arm-builds-then-configures",
        "arms-assign-two-names",
        "arms-return-and-assign",
        "arm-logs-then-builds",
        "empty-string-first-in-a-chain",
        "empty-string-first-in-a-match",
        "empty-string-last-in-a-chain",
        "empty-string-first-then-repeated",
        "empty-string-guard-first",
        "empty-string-guard-between",
        "conditional-expression-on-an-empty-string-first",
        "membership-on-non-names-first",
        "function-below-the-factory",
        "function-above-the-factory",
        "factory-as-conditional-expression",
        "short-switch-above-a-long-chain",
        "repeat-after-a-third-function",
        "arms-call-private-functions",
        "name-of-a-model",
    ],
)
def test_switches_on_a_variant_name_are_reported(source, expected):
    assert found(source) == expected


# Two operations over one closed set: the shape the rule prescribes.
CLOSED_TWICE = """
def renderer(fmt):
    match fmt:
        case "console":
            return pick()
        case "json":
            return "orjson"
        case _:
            assert_never(fmt)


def coloured(fmt):
    match fmt:
        case "console":
            return isatty()
        case "json":
            return False
        case _:
            assert_never(fmt)
"""


@pytest.mark.parametrize(
    "source",
    [
        # The factory: every arm builds and returns an object.
        "def build(backend):\n"
        "    if backend == 'modal':\n        return Modal()\n"
        "    elif backend == 'local':\n        return Local()\n"
        "    elif backend == 'slurm':\n        return Slurm()\n",
        "def build(kind, cfg):\n"
        "    if kind == 'api':\n        return Api(cfg)\n"
        "    elif kind == 'local':\n        return Local(cfg)\n"
        "    elif kind == 'batch':\n        return Batch(cfg)\n",
        # A classmethod constructor builds the object too (TYP-4).
        "def build(backend, cfg):\n"
        "    if backend == 'modal':\n        return Modal.from_config(cfg)\n"
        "    if backend == 'local':\n        return Local.from_config(cfg)\n"
        "    if backend == 'slurm':\n        return runners.Slurm.from_config(cfg)\n"
        "    raise UnknownBackendError(backend)\n",
        # The lazy import ARC-8 asks for comes before the object.
        "def optimizer(optim, params, *, lr):\n"
        "    if optim == 'adam':\n"
        "        from torch.optim import Adam\n\n"
        "        return Adam(params, lr=lr)\n"
        "    if optim == 'sgd':\n"
        "        from torch.optim import SGD\n\n"
        "        return SGD(params, lr=lr)\n"
        "    if optim == 'adamw':\n"
        "        import torch\n\n"
        "        return torch.optim.AdamW(params, lr=lr)\n"
        "    raise UnknownOptimizerError(optim)\n",
        # Every arm assigns the object to one name, returned after the chain.
        "def build(backend, cfg):\n"
        "    if backend == 'modal':\n        runner = ModalRunner(cfg)\n"
        "    elif backend == 'local':\n        runner = LocalRunner(cfg)\n"
        "    elif backend == 'slurm':\n        runner = SlurmRunner.of(cfg)\n"
        "    else:\n        raise UnknownBackendError(backend)\n"
        "    return runner\n",
        # The classes of the factory may be private to its module (STY-5).
        "def clock(kind_of_clock):\n"
        "    if kind_of_clock == 'wall':\n        return _Wall()\n"
        "    if kind_of_clock == 'cuda':\n        return _Cuda.from_env()\n"
        "    if kind_of_clock == 'fake':\n        return clocks._Fake()\n"
        "    raise UnknownClockError(kind_of_clock)\n",
        # A closed set that gains operations stays a match ending in `assert_never`.
        "def describe(shape):\n    match shape.form:\n"
        "        case 'circle':\n            draw()\n"
        "        case 'square':\n            fill()\n"
        "        case 'line':\n            stroke()\n"
        "        case _:\n            assert_never(shape.form)\n",
        # A second operation over the closed set is a second such match.
        CLOSED_TWICE,
        # A value that does not read as a name is tested, not switched on.
        "def as_int(text):\n    if text == '':\n        return None\n"
        "    return int(text)\n\n\n"
        "def as_float(text):\n    if text == '':\n        return None\n"
        "    return float(text)\n",
        "def sources(paths):\n    for p in paths:\n"
        "        if p.suffix == '.py':\n            yield p\n\n\n"
        "def module_name(p):\n    if p.suffix == '.py':\n"
        "        p = p.with_suffix('')\n    return '.'.join(p.parts)\n",
        # Such a test is no arm: two arms are left here, in a chain and in a run.
        "def run(mode):\n"
        "    if mode == '':\n        default()\n"
        "    elif mode == 'train':\n        train()\n"
        "    elif mode == 'eval':\n        evaluate()\n\n\n"
        "def render(rows, *, mode):\n"
        "    if mode == 'csv':\n        return to_csv(rows)\n"
        "    if mode == '':\n        return to_text(rows)\n"
        "    if mode == 'json':\n        return to_json(rows)\n",
        # The dispatch on a file suffix that STY-9 recommends.
        "def load(path):\n    match path.suffix:\n"
        "        case '.json':\n            return json.loads(path.read_text())\n"
        "        case '.yaml' | '.yml':\n"
        "            return yaml.safe_load(path.read_text())\n"
        "        case '.toml':\n            return tomllib.loads(path.read_text())\n"
        "        case _:\n            raise UnknownSuffixError(path.suffix)\n",
        # Names that torch, numpy and pandas own.
        "def synchronize(device):\n    if device.type == 'cuda':\n        wait()\n\n\n"
        "def pin_memory(self):\n    if self.device.type == 'cuda':\n"
        "        return True\n    return False\n\n\n"
        "def autocast(batch):\n    match batch.device.type:\n"
        "        case 'cuda':\n            half()\n"
        "        case 'mps':\n            single()\n"
        "        case 'cpu':\n            double()\n",
        "def is_text(df, column):\n    if df[column].dtype == 'object':\n"
        "        return True\n    return False\n\n\n"
        "def fill(array):\n    if array.dtype == 'object':\n"
        "        return array.astype(str)\n    return array\n",
        # A `kind` attribute is ARC-4's to report, in each of its three shapes.
        "def run(item):\n"
        "    if item.kind == 'api':\n        call_api()\n"
        "    elif item.kind == 'local':\n        call_local()\n"
        "    elif item.kind == 'batch':\n        call_batch()\n\n\n"
        "def cost(item):\n    match item.kind:\n"
        "        case 'api':\n            return price_api(item)\n"
        "        case 'local':\n            return free(item)\n"
        "        case 'batch':\n            return price_batch(item)\n\n\n"
        "def remote(item):\n    if item.kind in ('api', 'batch'):\n"
        "        return True\n    return False\n",
        # A membership test on a `kind` attribute or on the `type` of a device.
        "def remote(item):\n    if item.kind in ('api', 'batch'):\n"
        "        return True\n    return False\n\n\n"
        "def queued(item):\n    if item.kind in ('batch', 'queue'):\n"
        "        return True\n    return False\n\n\n"
        "def on_gpu(device):\n    if device.type in ('cuda', 'mps'):\n"
        "        return True\n    return False\n\n\n"
        "def pinned(self):\n    if self.device.type in ('cuda', 'mps'):\n"
        "        return True\n    return False\n",
        # Two arms in one function, different variant names elsewhere.
        "def a(x):\n    if x.mode == 'fast':\n        go()\n\n\n"
        "def b(x):\n    if x.split == 'fast':\n        go()\n",
        "if __name__ == '__main__':\n    main()\n",
        # The factory written as a conditional expression.
        "def build(cfg):\n    return Modal() if cfg.backend == 'modal' else Local()\n",
        # Deeper than the recursion limit.
        "def total(a):\n    return " + " + ".join(["a"] * 3000) + "\n",
    ],
    ids=[
        "factory",
        "factory-on-a-name-kind",
        "factory-through-classmethods",
        "factory-with-lazy-imports",
        "factory-that-assigns",
        "factory-of-private-classes",
        "closed-match",
        "closed-match-in-two-functions",
        "empty-string-in-two-functions",
        "file-suffix-in-two-functions",
        "two-arms-beside-an-empty-string",
        "match-on-file-suffix",
        "type-of-a-device",
        "dtype",
        "kind-attribute",
        "membership-of-kind-and-device-type",
        "different-names",
        "main-guard",
        "factory-as-conditional-expression",
        "long-sum",
    ],
)
def test_one_switch_in_one_place_passes(source):
    assert found(source) == []


def asked_twice(value: str, *, subject: str = "request.field") -> str:
    return (
        f"def first(request):\n    if {subject} == {value!r}:\n        go()\n\n\n"
        f"def second(request):\n    if {subject} == {value!r}:\n        stop()\n"
    )


@pytest.mark.parametrize("value", ["modal", "linear-warmup", "gpt-4.1", "POST", "v2"])
def test_a_string_that_reads_as_a_name_is_a_variant_value(value):
    assert found(asked_twice(value)) == [(7, "ARC-9")]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "\n",
        ".py",
        "r",
        "application/json",
        "POST /x",
        "signed integer",
        "8080",
        "_private",
    ],
    ids=[
        "empty",
        "newline",
        "file-suffix",
        "one-letter",
        "media-type",
        "request-line",
        "two-words",
        "number",
        "leading-underscore",
    ],
)
def test_a_string_that_does_not_read_as_a_name_is_not_a_variant_value(value):
    assert found(asked_twice(value)) == []


@pytest.mark.parametrize(
    "subject",
    [
        "name",
        "cfg.model.name",
        "self.name",
        "path.name",
        "platform",
        "cfg.platform",
        "os",
        "cfg.os",
    ],
)
def test_a_name_of_the_project_is_a_variant_name_whatever_it_is(subject):
    assert found(asked_twice("modal", subject=subject)) == [(7, "ARC-9")]


@pytest.mark.parametrize(
    ("subject", "value"),
    [
        ("os.name", "posix"),
        ("sys.platform", "darwin"),
        ("sys.implementation.name", "pypy"),
        ("platform.system()", "Linux"),
        ("platform.machine()", "arm64"),
        ("__name__", "demo"),
        ("type(request).__name__", "Request"),
        ("type(request).__qualname__", "Request"),
        ("request.__module__", "builtins"),
        ("request.dtype", "object"),
    ],
    ids=[
        "os-name",
        "sys-platform",
        "implementation-name",
        "platform-system",
        "platform-machine",
        "module-name",
        "class-name",
        "qualname",
        "module-of",
        "dtype",
    ],
)
def test_a_name_that_python_or_a_library_owns_is_no_variant_name(subject, value):
    assert found(asked_twice(value, subject=subject)) == []


def test_a_test_on_mixed_values_keeps_the_ones_that_read_as_names():
    source = (
        "def first(mode):\n    if mode in ('', 'train'):\n        go()\n\n\n"
        "def second(mode):\n    if mode == 'train':\n        stop()\n\n\n"
        "def third(mode):\n    if mode in ('', 'r'):\n        wait()\n"
    )

    assert found(source) == [(7, "ARC-9")]


@pytest.mark.parametrize(
    "source",
    [EMPTY_FIRST, EMPTY_FIRST_IN_A_MATCH, EMPTY_LAST, EMPTY_GUARD_FIRST],
    ids=["first-in-a-chain", "first-in-a-match", "last-in-a-chain", "guard-first"],
)
def test_a_test_on_a_string_that_does_not_read_as_a_name_is_no_arm(source):
    [finding] = switches.check(ast.parse(source), "src/demo/runner.py")

    assert finding.message.startswith("3 arms on `")


# A third function on the value of `SHOTGUN`, to follow it.
LABEL = "\n\ndef label(cfg):\n    if cfg.backend == 'modal':\n        return 'cloud'\n"


def test_a_waived_switch_does_not_count_against_the_others_of_its_module():
    assert found(SHOTGUN, waived=frozenset({3})) == []
    assert found(SHOTGUN + LABEL) == [(10, "ARC-9"), (16, "ARC-9")]


def test_the_switch_below_a_waived_one_is_the_first_that_the_others_repeat():
    tree = ast.parse(SHOTGUN + LABEL)

    [finding] = switches.check(tree, "src/demo/runner.py", waived=frozenset({3}))

    assert finding.line == 16
    assert "`cost` (line 10)" in finding.message


# A fourth function on a value of `EMPTY_GUARD_FIRST`.
HEADER = "\n\ndef header(fmt):\n    if fmt == 'csv':\n        return 'a,b'\n"


@pytest.mark.parametrize(
    "line", [3, 5, 9], ids=["guard-with-no-arm", "first-arm", "last-arm"]
)
def test_a_waiver_above_any_if_of_a_run_of_guards_waives_the_run(line):
    assert found(EMPTY_GUARD_FIRST + HEADER) == [(5, "ARC-9"), (15, "ARC-9")]
    assert found(EMPTY_GUARD_FIRST + HEADER, waived=frozenset({line})) == []


@pytest.mark.parametrize(
    ("source", "line", "named"),
    [
        (THIRD_FIRST, 13, "`start` (line 8)"),
        (COST_THEN_FACTORY, 3, "`build` (line 9)"),
    ],
    ids=["repeat-after-a-third-function", "function-above-the-factory"],
)
def test_a_repeat_names_the_switch_it_shares_a_value_with(source, line, named):
    [finding] = switches.check(ast.parse(source), "src/demo/runner.py")

    assert finding.line == line
    assert named in finding.message


def test_a_match_that_ends_in_assert_never_is_no_switch_for_another_module():
    assert switches.switches_of(ast.parse(CLOSED_TWICE)) == []


START = (
    "def start(cfg):\n"
    "    if cfg.backend == 'modal':\n        launch()\n"
    "    elif cfg.backend == 'local':\n        run()\n"
)
COST = "def cost(cfg):\n    if cfg.backend == 'modal':\n        return bill()\n"
COST_IN_ONE_LINE = "def cost(cfg):\n    return 0.3 if cfg.backend == 'modal' else 0.0\n"


@pytest.mark.parametrize(
    "source", [COST, COST_IN_ONE_LINE], ids=["statement", "conditional-expression"]
)
def test_a_switch_repeated_in_another_module_is_reported_with_its_place(source):
    other = switches.Elsewhere(
        "src/demo/start.py", switches.switches_of(ast.parse(START))[0]
    )

    findings = switches.check(
        ast.parse(source), "src/demo/cost.py", elsewhere=lambda: [other]
    )

    assert [(f.line, f.rule) for f in findings] == [(2, "ARC-9")]
    assert "`start` (src/demo/start.py:2)" in findings[0].message


FACTORY = (
    "def build(cfg):\n"
    "    if cfg.backend == 'modal':\n        return Modal()\n"
    "    elif cfg.backend == 'local':\n        return Local()\n"
)
FACTORY_THROUGH_CLASSMETHODS = (
    "def build(cfg):\n"
    "    if cfg.backend == 'modal':\n        return Modal.from_config(cfg)\n"
    "    elif cfg.backend == 'local':\n        return Local.from_config(cfg)\n"
)
FACTORY_THAT_ASSIGNS = (
    "def build(cfg):\n"
    "    if cfg.backend == 'modal':\n"
    "        from demo.modal import Modal\n\n        runner = Modal(cfg)\n"
    "    elif cfg.backend == 'local':\n        runner = Local(cfg)\n"
    "    else:\n        raise UnknownBackendError(cfg.backend)\n"
    "    return runner\n"
)
FACTORY_IN_ONE_LINE = (
    "def build(cfg):\n    return Modal() if cfg.backend == 'modal' else Local()\n"
)
FACTORIES = [
    FACTORY,
    FACTORY_THROUGH_CLASSMETHODS,
    FACTORY_THAT_ASSIGNS,
    FACTORY_IN_ONE_LINE,
]
FACTORY_IDS = [
    "factory",
    "factory-through-classmethods",
    "factory-that-assigns",
    "factory-as-conditional-expression",
]


@pytest.mark.parametrize("source", FACTORIES, ids=FACTORY_IDS)
def test_a_switch_on_a_value_of_a_factory_in_another_module_is_reported(source):
    other = switches.Elsewhere(
        "src/demo/build.py", switches.switches_of(ast.parse(source))[0]
    )

    findings = switches.check(
        ast.parse(COST), "src/demo/cost.py", elsewhere=lambda: [other]
    )

    assert [(f.line, f.rule) for f in findings] == [(2, "ARC-9")]
    assert "`build` (src/demo/build.py:2)" in findings[0].message


@pytest.mark.parametrize(
    "source",
    [
        "def run(cfg):\n    return launch(cfg.backend)\n",
        LONG_CHAIN,
        *FACTORIES,
        CLOSED_TWICE,
    ],
    ids=["no-switch", "long-chain-reported-already", *FACTORY_IDS, "closed-match"],
)
def test_other_modules_are_read_only_for_a_switch_they_could_repeat(source):
    def unread() -> list[switches.Elsewhere]:
        raise AssertionError("the package was read")

    switches.check(ast.parse(source), "src/demo/runner.py", elsewhere=unread)

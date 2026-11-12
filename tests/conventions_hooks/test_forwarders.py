"""A function that only forwards its parameters is reported, and no other wrapper."""

from __future__ import annotations

import pytest

from conventions_hooks.conventions import check_file

STORE = (
    "registry = Registry()\n\n\nclass Store: ...\n\n\ndef save(*args, **kwargs): ...\n"
)
SAVE = "from demo.store import save\n\n\n"


@pytest.mark.parametrize(
    ("source", "callee"),
    [
        (
            SAVE + "def persist(item, *, force):\n    return save(item, force=force)\n",
            "save",
        ),
        (
            "from . import store\n\n\ndef persist(*args, **kwargs):\n"
            "    store.save(*args, **kwargs)\n",
            "store.save",
        ),
        (
            "import demo.store\n\n\ndef persist(item):\n"
            "    return demo.store.save(item)\n",
            "demo.store.save",
        ),
        (
            "def _save(item):\n    ...\n\n\ndef persist(item):\n"
            '    """Persist one item."""\n    return _do(item)\n\n\n'
            "def _persist(item):\n    return _save(item)\n",
            "_save",
        ),
        (SAVE + "async def persist(item):\n    return await save(item)\n", "save"),
        (SAVE + "def persist(item, /):\n    return save(item)\n", "save"),
    ],
    ids=[
        "keywords",
        "star-arguments",
        "module-path",
        "private-to-private",
        "awaited",
        "positional-only",
    ],
)
def test_a_function_that_only_forwards_is_reported(demo_package, source, callee):
    demo = demo_package({"store.py": STORE, "api.py": source})

    found = check_file(demo / "api.py")

    assert [f.rule for f in found] == ["ARC-10"]
    assert f"forwards its arguments to `{callee}`;" in found[0].message


@pytest.mark.parametrize(
    "source",
    [
        # Changes or adds an argument: it hides something.
        SAVE + "def persist(item):\n    return save(item, force=True)\n",
        SAVE + "def persist(item, path):\n    return save(path, item)\n",
        SAVE + "def persist(first, *rest):\n    return save(*rest, first)\n",
        SAVE
        + "def persist(item, *, force=False):\n    return save(item, force=force)\n",
        SAVE + "def persist(item, /):\n    return save(item=item)\n",
        # Nothing to forward: a console script's `main`.
        SAVE + "def main():\n    save()\n",
        # Calls outside the package: an adapter over a dependency.
        "import yaml\n\n\ndef load(text):\n    return yaml.safe_load(text)\n",
        "from yaml import dump\n\n\ndef export():\n"
        "    from demo.store import dump\n\n    return dump\n\n\n"
        "def write(text):\n    return dump(text)\n",
        # Builds an object, or goes through one.
        "from demo.store import Store\n\n\ndef build(config):\n"
        "    return Store(config)\n",
        "from demo.store import registry\n\n\ndef register(item):\n"
        "    return registry.add(item)\n",
        SAVE + "def apply(save, item):\n    return save(save, item)\n",
        # A public name over a private implementation is the interface.
        "def _save(item):\n    ...\n\n\ndef save(item):\n    return _save(item)\n",
        # Registrations and methods are left alone.
        SAVE + "@app.command()\ndef persist(item):\n    return save(item)\n",
        SAVE
        + "class Store:\n    def persist(self, item):\n        return save(item)\n",
        SAVE
        + "def persist(item):  # conventions: ARC-10 - the public name of `save`.\n"
        "    return save(item)\n",
    ],
    ids=[
        "adds-argument",
        "reorders",
        "reorders-star",
        "adds-default",
        "positional-only-by-keyword",
        "no-parameters",
        "third-party",
        "imported-in-another-function",
        "builds-object",
        "method-of-object",
        "parameter-is-called",
        "private-implementation",
        "decorated",
        "method",
        "allowed",
    ],
)
def test_a_function_that_does_more_than_forward_passes(demo_package, source):
    demo = demo_package({"store.py": STORE, "api.py": source})

    assert check_file(demo / "api.py") == []

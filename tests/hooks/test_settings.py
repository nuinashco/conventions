"""The nearest pyproject.toml's `[tool.conventions]` table opts a repo in."""

from __future__ import annotations

import pytest

from conventions_hooks.settings import Settings, SettingsError


def test_a_repo_opts_in_with_the_table_and_ignores_what_it_lists(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.conventions]\nignore = ["STY-4", "DOC-7"]\n'
    )
    (tmp_path / "src" / "x").mkdir(parents=True)

    settings = Settings.of(tmp_path / "src" / "x" / "module.py")

    assert settings == Settings(enabled=True, ignore=frozenset({"STY-4", "DOC-7"}))
    assert (settings.keeps("STY-4"), settings.keeps("STY-5")) == (False, True)


def test_a_repo_without_the_table_or_without_pyproject_is_not_opted_in(tmp_path):
    (tmp_path / "with" / "pyproject.toml").parent.mkdir()
    (tmp_path / "with" / "pyproject.toml").write_text('[project]\nname = "x"\n')

    assert not Settings.of(tmp_path / "with" / "module.py").enabled
    assert not Settings.of(tmp_path / "module.py").enabled


def test_the_nearest_pyproject_decides_even_without_the_table(opted_in):
    member = opted_in / "packages" / "member"
    member.mkdir(parents=True)
    (member / "pyproject.toml").write_text('[project]\nname = "member"\n')

    assert Settings.of(opted_in / "module.py").enabled
    assert not Settings.of(member / "module.py").enabled


@pytest.mark.parametrize(
    ("toml", "problem"),
    [
        ('[tool.conventions]\nignore = "STY-4"\n', "must list rule IDs"),
        ('[tool.conventions]\nignore = ["sty4"]\n', "must list rule IDs"),
        ('[tool.conventions]\nignores = ["STY-4"]\n', "unknown key ignores"),
        ("[tool.conventions\n", "cannot read it as TOML"),
        ('[tool]\nconventions = "on"\n', "must be a table"),
    ],
    ids=["string", "not-an-id", "unknown-key", "broken-toml", "not-a-table"],
)
def test_a_malformed_table_is_an_error_naming_the_problem(tmp_path, toml, problem):
    (tmp_path / "pyproject.toml").write_text(toml)

    with pytest.raises(SettingsError, match=problem):
        Settings.of(tmp_path)

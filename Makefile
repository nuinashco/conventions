.DEFAULT_GOAL := help
.PHONY: help setup lint format typecheck test build test-judges check

help:  ## show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

setup:  ## create the venv and install the git hooks
	uv sync
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

lint:  ## ruff lint + format check, no changes
	uv run ruff check
	uv run ruff format --check

format:  ## ruff auto-fix + format
	uv run ruff check --fix
	uv run ruff format

typecheck:  ## pyright
	uv run pyright

test:  ## unit tests of the hooks and the generator, and that generated files are fresh
	uv run pytest

build:  ## regenerate GUIDE.md, COVERAGE.md and the plugin's skills and subagents from rules/ and agents/
	uv run build-rules

test-judges:  ## run the Claude judges on their labelled cases (live `claude` calls, costs tokens)
	uv run pytest -m judges -v

check: lint typecheck test  ## everything CI runs
	uv run build-rules --check

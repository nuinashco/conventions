.DEFAULT_GOAL := help
# The judged fixture projects carry planted mistakes.
PYTHON_FILES = $$(git ls-files -co --exclude-standard '*.py' ':!tests/judges/fixtures')
.PHONY: help setup github lint format typecheck test build test-judges check

help:  ## show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

setup:  ## create the venv and install the git hooks
	uv sync
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

github:  ## once per GitHub repo: squash-merge only, PR title as the commit, merged branches deleted
	gh api -X PATCH "repos/{owner}/{repo}" --silent \
		-F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
		-f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=BLANK \
		-F delete_branch_on_merge=true

lint:  ## ruff and this repo's own checks on every Python file, no changes
	uv run ruff check
	uv run ruff format --check
	uv run check-comments $(PYTHON_FILES)
	uv run check-conventions $(PYTHON_FILES)

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

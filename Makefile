.DEFAULT_GOAL := help
.PHONY: help lint test test-templates

help:  ## show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

lint:  ## ruff on the hooks package and the tests
	uv run ruff check src tests
	uv run ruff format --check src tests

test:  ## unit tests of the hooks package
	uv run pytest

test-templates:  ## render every profile and run its own `make check` (slow: uv sync per render, needs network)
	uv run pytest -m templates

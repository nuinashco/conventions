.DEFAULT_GOAL := help
.PHONY: help test-templates

help:  ## show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

test-templates:  ## render every profile and run its own `make check` (slow: uv sync per render, needs network)
	uv run --no-project --python 3.14 --with copier --with pytest pytest tests

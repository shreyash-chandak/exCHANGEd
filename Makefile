.PHONY: install test test-live lint fmt

install:
	uv sync

test:
	uv run pytest -q -m "not live"

test-live:
	CHANGE_LIVE=1 uv run pytest -q -m live

lint:
	uv run ruff check . && uv run ruff format --check .

fmt:
	uv run ruff format . && uv run ruff check --fix .

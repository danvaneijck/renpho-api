.PHONY: test lint check

test:
	uv run --extra dev pytest tests/ -v --cov=renpho --cov-report=term-missing

lint:
	uv run --extra dev ruff check .

check: lint test

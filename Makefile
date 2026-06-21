.PHONY: install dev lint test clean

install:
	pip install -e ".[dev]"

dev:
	uvicorn judicial_evidence_agent.api.main:app --reload --port 8000

lint:
	ruff check src tests

test:
	pytest -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

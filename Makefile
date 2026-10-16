PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest
UVICORN ?= .venv/bin/uvicorn

.PHONY: up seed probe test dev web eval load reset clean

up:
	docker compose up -d falkordb

seed:
	$(PYTHON) seed/seed.py

probe:
	$(PYTHON) scripts/probe_falkordb.py

test:
	$(PYTEST) tests/

dev:
	$(UVICORN) backend.main:app --host 0.0.0.0 --port 8000 --reload

web:
	npm --prefix frontend run dev

eval:
	$(PYTHON) evals/run_evals.py

load:
	$(PYTHON) scripts/load_test.py

reset:
	$(PYTHON) seed/seed.py --reset

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ probe_results.json

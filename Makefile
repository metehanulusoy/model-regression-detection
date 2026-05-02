.PHONY: help install test lint typecheck check fmt clean run drift docker

help:
	@echo "Targets:"
	@echo "  install     pip install -e .[dev]"
	@echo "  test        pytest with coverage"
	@echo "  lint        ruff check"
	@echo "  typecheck   mypy --strict"
	@echo "  check       lint + typecheck + test"
	@echo "  fmt         ruff format + ruff check --fix"
	@echo "  run         mrd run --prompt customer_support --dataset golden/customer_support.jsonl --baseline auto"
	@echo "  drift       mrd drift --prompt customer_support"
	@echo "  docker      build the docker image"
	@echo "  clean       remove caches and reports"

install:
	python3 -m pip install -e ".[dev]"

test:
	pytest --cov

lint:
	ruff check src tests

typecheck:
	mypy src

check: lint typecheck test

fmt:
	ruff format src tests
	ruff check src tests --fix

run:
	mrd run --prompt customer_support --dataset golden/customer_support.jsonl --baseline auto --report-dir reports

drift:
	mrd drift --prompt customer_support

docker:
	docker build -t model-regression-detection:local .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov build dist *.egg-info reports
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

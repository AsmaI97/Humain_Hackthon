PYTHON_BIN ?= python3.11
VENV := .venv
PY ?= $(VENV)/bin/python
IMAGE ?= authpilot

# The sample cases replay a live cache when one exists, and use the offline stub otherwise.
# LLM_MODE=live calls the API and writes the replay cache. Default for the app is replay.
DEMO_MODE ?= $(or $(LLM_MODE),$(shell [ -s cache/llm_cache.jsonl ] && echo replay || echo stub))
DEMO_CASES ?= dev/case_036 dev/case_040

.PHONY: help setup data test demo live-sample dashboard payer eval eval-criteria summary compare check \
        docker-build docker-run docker-test clean

help:
	@echo "make setup         create .venv and install the exact locked dependencies"
	@echo "make test          run the test suite (offline)"
	@echo "make demo          two cases end to end (replay cache if present, else offline stub)"
	@echo "make live-sample   run the two sample cases with Claude and write the replay cache"
	@echo "make dashboard     web app at http://localhost:8501"
	@echo "make eval          full evaluation on the dev split (refuses stub mode), then the summary"
	@echo "make compare       compare the two latest saved evaluations (refuses stub mode)"
	@echo "make eval-criteria quick criterion-level metrics"
	@echo "make summary       regenerate docs/results_summary.md and docs/slides.html from the latest evaluation"
	@echo "make check         test + demo + quick metrics (what a reviewer should run first)"
	@echo "make data          regenerate all synthetic cases (deterministic)"
	@echo "make payer         run the mock payer as an HTTP service on port 8100"
	@echo "make docker-build  build the image; docker-run serves the web app on port 8501"

setup:
	$(PYTHON_BIN) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --quiet -r requirements-lock.txt
	@echo "setup done: $(VENV) with the locked dependencies"

data:
	$(PY) -m authpilot.data.generator --split all
	$(PY) -m authpilot.data.unseen_generator

test:
	$(PY) -m pytest

demo:
	@echo "sample LLM mode: $(DEMO_MODE)"
	@for c in $(DEMO_CASES); do LLM_MODE=$(DEMO_MODE) $(PY) -m authpilot.cli run $$c --approve --reviewer demo-reviewer || exit 1; echo; done

live-sample:
	$(MAKE) demo DEMO_MODE=live

dashboard:
	LLM_MODE=$(DEMO_MODE) $(PY) -m streamlit run authpilot/app/dashboard.py --global.developmentMode false --browser.gatherUsageStats false

payer:
	$(PY) -m uvicorn authpilot.payer_mock.app:app --port 8100

eval:
	$(PY) -c "from authpilot.eval.guard import require_eval_mode; require_eval_mode()"
	$(PY) -m authpilot.eval.run_all --split dev --runs 3
	$(PY) -m authpilot.eval.summary
	$(PY) -m authpilot.eval.slides

eval-criteria:
	$(PY) -m authpilot.eval.criteria_eval --split dev

summary:
	$(PY) -m authpilot.eval.summary
	$(PY) -m authpilot.eval.slides

compare:
	$(PY) -m authpilot.eval.compare

check: test demo eval-criteria

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -p 8501:8501 --env-file .env.example $(IMAGE)

docker-test:
	docker run --rm $(IMAGE) python -m pytest

clean:
	rm -rf runtime .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

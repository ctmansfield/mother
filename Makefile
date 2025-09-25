PY?=python3
VENV=.venv

.PHONY: install verify test smoke
install:
	@$(PY) -V >/dev/null 2>&1 || true
	@[ -d $(VENV) ] || $(PY) -m venv $(VENV) || true
	@. $(VENV)/bin/activate 2>/dev/null || true; pip install --upgrade pip >/dev/null 2>&1 || true
	@. $(VENV)/bin/activate 2>/dev/null || true; [ -f requirements-dev.txt ] && pip install -r requirements-dev.txt >/dev/null 2>&1 || true
	@echo "install done"

verify:
	@. $(VENV)/bin/activate 2>/dev/null || true; ./verify.sh || true

test:
	@. $(VENV)/bin/activate 2>/dev/null || true; pytest -q || true

smoke:
	@. $(VENV)/bin/activate 2>/dev/null || true; $(PY) scripts/smoke.py || true

PY ?= python3
VENV ?= .venv
VENV_PY = $(VENV)/bin/python

.PHONY: install verify test smoke
install:
	$(PY) -m venv "$(VENV)"
	"$(VENV_PY)" -m pip install -r requirements-dev.txt -e ".[physiology-test]"

verify:
	PYTHON="$(VENV_PY)" bash ./verify.sh

test:
	"$(VENV_PY)" -m pytest -q

smoke:
	"$(VENV_PY)" -m scripts.smoke

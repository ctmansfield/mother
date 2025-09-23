# One shell per target; use ">" instead of TAB.
.ONESHELL:
.RECIPEPREFIX := >
SHELL := /bin/bash

ROOT := $(CURDIR)
OPS_DIR := $(ROOT)/ops
COMPOSE := docker compose -f $(OPS_DIR)/docker-compose.yml

.PHONY: help build up down restart logs tail health demo api-shell install-edit clean validate-pp precommit-install precommit-run

help:
> echo "Targets:"
> echo "  build            Rebuild API (no cache) and start"
> echo "  up               Start API"
> echo "  down             Stop stack (and remove volumes)"
> echo "  restart          Restart API"
> echo "  logs             Show last 200 API log lines"
> echo "  tail             Follow API logs"
> echo "  health           Curl health endpoint (with retry)"
> echo "  demo             Curl demo endpoint"
> echo "  api-shell        Bash shell in API container"
> echo "  install-edit     Run 'pip install -e .' in API container"
> echo "  clean            Remove build artifacts on host"
> echo "  validate-pp      Validate pyproject.toml locally"
> echo "  precommit-install  Install git pre-commit hooks"
> echo "  precommit-run      Run hooks against all files"

build:
> $(COMPOSE) down -v
> docker builder prune -f
> $(COMPOSE) build --no-cache mother-api
> $(COMPOSE) up -d mother-api

up:
> $(COMPOSE) up -d mother-api

down:
> $(COMPOSE) down -v

restart:
> $(COMPOSE) restart mother-api || $(COMPOSE) up -d mother-api

logs:
> $(COMPOSE) logs --no-log-prefix mother-api | tail -n 200

tail:
> $(COMPOSE) logs -f --no-log-prefix mother-api

health:
> set -e
> for i in {1..20}; do
>   if curl -fsS http://localhost:8000/health >/dev/null; then
>     curl -s http://localhost:8000/health && echo
>     exit 0
>   fi
>   echo "waiting for API... ($$i/20)"; sleep 0.5
> done
> echo "API did not become healthy in time" >&2; exit 1

demo:
> curl -fsS http://localhost:8000/nudge/demo | jq .

api-shell:
> $(COMPOSE) exec mother-api bash -lc 'pwd; ls -la'

install-edit:
> $(COMPOSE) exec mother-api bash -lc 'pip install -e .'

clean:
> rm -rf $(ROOT)/*.egg-info $(ROOT)/build $(ROOT)/dist

validate-pp:
> python - <<'PY'
> import pathlib
> try:
>     import tomllib  # 3.11+
> except ModuleNotFoundError:
>     import tomli as tomllib  # <=3.10
> tomllib.loads(pathlib.Path("pyproject.toml").read_text())
> print("pyproject.toml ✅ OK")
> PY

precommit-install:
> python -m pip install --upgrade pre-commit
> pre-commit install

precommit-run:
> pre-commit run --all-files

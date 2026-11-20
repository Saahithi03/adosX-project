# DealerOS take-home. Targets are added as each build step lands.
# Requires: GNU make, Docker (with compose v2), Python 3.12.

ifeq ($(OS),Windows_NT)
  PY_BOOT ?= py -3.12
  VENV_BIN := .venv/Scripts
else
  PY_BOOT ?= python3.12
  VENV_BIN := .venv/bin
endif

PY     := $(VENV_BIN)/python
MANAGE := $(PY) backend/manage.py

.PHONY: setup venv db-up db-down db-reset migrate seed ingest api test rls-off rls-on check dbshell-app dbshell-owner

## setup: venv + deps, start Postgres, run migrations, seed demo users
setup: venv db-up migrate seed

## venv: create .venv and install backend requirements
venv: .venv/.installed

# Stamp file: re-installs only when requirements.txt changes.
.venv/.installed: backend/requirements.txt
	$(PY_BOOT) -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r backend/requirements.txt
	@echo ok > $@

## db-up: start Postgres and wait until it is healthy
db-up:
	docker compose up -d --wait db

## db-down: stop Postgres (data kept)
db-down:
	docker compose down

## db-reset: destroy the data volume and start fresh (re-runs the role init script)
db-reset:
	docker compose down -v
	docker compose up -d --wait db

# Owner-only targets. Target-specific `export` sets the variable in the
# recipe's environment without relying on sh-style `VAR=x cmd` syntax.
migrate seed ingest rls-off rls-on: export DEALEROS_DB_ROLE = owner

## migrate: apply migrations as dealeros_owner (the table owner)
migrate:
	$(MANAGE) migrate

## seed: create demo users alice (ORG-A) and bob (ORG-B)
seed:
	$(MANAGE) seed

## ingest: reconcile data/*.csv and store exceptions (owner, one org at a time under RLS)
ingest:
	$(MANAGE) ingest

## test: run the test suite as dealeros_app (never the owner)
test:
	$(PY) -m pytest -c backend/pytest.ini --rootdir backend

## rls-off / rls-on: isolation walkthrough. After rls-off, `make test` must FAIL.
rls-off:
	$(MANAGE) rls off

rls-on:
	$(MANAGE) rls on

## api: Django dev server on :8000, connected as the app role
api:
	$(MANAGE) runserver 8000

## check: Django system check (as the app role)
check:
	$(MANAGE) check

## dbshell-app / dbshell-owner: psql inside the container as either role
dbshell-app:
	docker compose exec db psql -U dealeros_app -d dealeros

dbshell-owner:
	docker compose exec db psql -U dealeros_owner -d dealeros

# gammonNet — cibles de développement
#
# Ce dépôt évalue une position. Il ne connaît pas ses appelants. Voir CLAUDE.md.
#
#   make setup   installe l'environnement Python et récupère les sources tierces
#   make build   compile la bibliothèque d'inférence (cible native)
#   make test    joue la suite de tests
#   make bench   joue le banc de débit
#   make env     consigne la machine et la chaîne d'outils d'une mesure

SHELL := /bin/bash
VENV ?= $(HOME)/venv-gammonnet
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTHON_SYS ?= python3.12

VENDOR := vendor
REFERENCE := $(VENDOR)/backgammon-ai-engine

.PHONY: all setup venv vendor build test bench env clean help

all: help

help:
	@grep -E '^#   make' Makefile | sed 's/^#   //'

# ── Amorçage ─────────────────────────────────────────────────────────

setup: venv vendor

venv:
	@test -d $(VENV) || $(PYTHON_SYS) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install torch numpy gnubg-nn pytest

vendor:
	$(PYTHON) tools/fetch_vendor.py

env:
	$(PYTHON) tools/env_report.py

# ── Compilation ──────────────────────────────────────────────────────

build:
	@echo "rien à compiler pour l'instant (T01 introduira src/)"

# ── Mesure ───────────────────────────────────────────────────────────

test:
	$(PYTHON) -m pytest tests/ -v

bench:
	@echo "banc de débit : T05"

clean:
	rm -rf build/
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

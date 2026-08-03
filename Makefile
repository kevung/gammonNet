# gammonNet — cibles de développement
#
# Ce dépôt évalue une position. Il ne connaît pas ses appelants. Voir CLAUDE.md.
#
#   make setup   installe l'environnement Python et récupère les sources tierces
#   make build   compile la bibliothèque d'inférence (cible native)
#   make corpus  régénère le corpus figé de positions (déterministe)
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

.PHONY: all setup venv vendor build corpus test bench env clean help

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

CC ?= gcc
BUILD := build
LIBRARY := $(BUILD)/libgammonnet.so

# Nos sources sont tenues au silence complet du compilateur.
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -fPIC
# Les sources vendorées ne sont pas les nôtres à corriger : on les compile sans
# -Wextra plutôt que de les modifier, ce qui compliquerait chaque mise à jour du
# commit épinglé.
VENDOR_CFLAGS ?= -O2 -std=c11 -Wall -fPIC

INCLUDES := -Isrc -I$(REFERENCE)/c_engine

build: $(LIBRARY)

SOURCES := src/gn_rules_reference.c src/gn_encoding.c src/gn_position_id.c
HEADERS := src/gn_rules.h src/gn_encoding.h src/gn_position_id.h
OBJECTS := $(patsubst src/%.c,$(BUILD)/%.o,$(SOURCES))

$(BUILD)/%.o: src/%.c $(HEADERS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

$(BUILD)/bg_engine.o: $(REFERENCE)/c_engine/bg_engine.c
	@mkdir -p $(BUILD)
	$(CC) $(VENDOR_CFLAGS) $(INCLUDES) -c $< -o $@

$(LIBRARY): $(OBJECTS) $(BUILD)/bg_engine.o
	$(CC) -shared -o $@ $^ -lm
	@echo "→ $@"

corpus:
	$(PYTHON) tools/build_corpus_t01.py

# ── Mesure ───────────────────────────────────────────────────────────

test: build
	$(PYTHON) -m pytest tests/ -q

bench:
	@echo "banc de débit : T05"

clean:
	rm -rf build/
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

# gammonNet — cibles de développement
#
# Ce dépôt évalue une position. Il ne connaît pas ses appelants. Voir CLAUDE.md.
#
#   make setup   installe l'environnement Python et récupère les sources tierces
#   make build   compile la bibliothèque d'inférence (cible native)
#   make model   exporte les poids de référence vers models/*.bin
#   make corpus  régénère le corpus figé de positions (déterministe)
#   make test    joue la suite de tests
#   make bench   joue le banc de débit
#   make env     consigne la machine et la chaîne d'outils d'une mesure

SHELL := /bin/bash
VENV ?= $(HOME)/venv-gammonnet
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# Le Python système. Les distributions ne livrent pas toutes la même version :
# `mochy` passe par le module AppStream python3.12 de RHEL 8, la machine de
# bureau n'a que 3.13 et 3.14. Voir « Répartition entre machines » dans PLAN.md.
PYTHON_SYS ?= python3.12

# PyTorch : le paquet par défaut tire la build CUDA sur Linux, soit environ
# 5 Gio de paquets `nvidia-*`. C'est ce qu'il faut sur `mochy` (2 x RTX 4090) et
# c'est à éviter partout ailleurs. Sur une machine sans GPU :
#
#   make setup PYTHON_SYS=python3.13 TORCH_CPU=1 ORACLE=0
#
TORCH_CPU ?= 0
TORCH_INDEX := $(if $(filter-out 0,$(TORCH_CPU)),--index-url https://download.pytorch.org/whl/cpu,)

# L'oracle GNU Backgammon n'est utile que là où l'on mesure la force (T03, T11,
# T35). La piste navigateur n'en a pas besoin, et `gnubg-nn` se compile depuis
# ses sources — autant ne pas l'imposer à une machine qui ne s'en servira pas.
ORACLE ?= 1

VENDOR := vendor
REFERENCE := $(VENDOR)/backgammon-ai-engine

.PHONY: all setup venv vendor build model corpus test bench env clean help

all: help

help:
	@grep -E '^#   make' Makefile | sed 's/^#   //'

# ── Amorçage ─────────────────────────────────────────────────────────

setup: venv vendor

venv:
	@test -d $(VENV) || $(PYTHON_SYS) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install $(TORCH_INDEX) torch
	$(PIP) install numpy pytest
	@test "$(ORACLE)" = "0" && echo "oracle GNU Backgammon : ignoré (ORACLE=0)" || $(PIP) install gnubg-nn

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

INCLUDES := -Isrc -I$(REFERENCE)/c_engine -I$(REFERENCE)/c_inference

build: $(LIBRARY)

SOURCES := src/gn_rules_reference.c src/gn_encoding.c src/gn_position_id.c \
           src/gn_infer_reference.c
HEADERS := src/gn_rules.h src/gn_encoding.h src/gn_position_id.h src/gn_infer.h
OBJECTS := $(patsubst src/%.c,$(BUILD)/%.o,$(SOURCES))

# Sources vendorées, compilées telles quelles — voir VENDOR_CFLAGS.
VENDOR_OBJECTS := $(BUILD)/bg_engine.o $(BUILD)/nn_eval.o

$(BUILD)/%.o: src/%.c $(HEADERS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

$(BUILD)/bg_engine.o: $(REFERENCE)/c_engine/bg_engine.c
	@mkdir -p $(BUILD)
	$(CC) $(VENDOR_CFLAGS) $(INCLUDES) -c $< -o $@

$(BUILD)/nn_eval.o: $(REFERENCE)/c_inference/nn_eval.c
	@mkdir -p $(BUILD)
	$(CC) $(VENDOR_CFLAGS) $(INCLUDES) -c $< -o $@

$(LIBRARY): $(OBJECTS) $(VENDOR_OBJECTS)
	$(CC) -shared -o $@ $^ -lm
	@echo "→ $@"

# ── Modèle ───────────────────────────────────────────────────────────

MODEL := models/cubeless_prob5_512_512_256_128.bin

model: $(MODEL)

$(MODEL):
	$(PYTHON) tools/export_model.py

corpus:
	$(PYTHON) tools/build_corpus_t01.py

# ── Mesure ───────────────────────────────────────────────────────────

test: build
	$(PYTHON) -m pytest tests/ -q

bench: build
	$(PYTHON) bench/bench_throughput.py

clean:
	rm -rf build/
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

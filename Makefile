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
# la machine de calcul passe par le module AppStream python3.12 de RHEL 8, la machine de
# bureau n'a que 3.13 et 3.14. Voir « Répartition entre machines » dans PLAN.md.
PYTHON_SYS ?= python3.12

# PyTorch : le paquet par défaut tire la build CUDA sur Linux, soit environ
# 5 Gio de paquets `nvidia-*`. C'est ce qu'il faut sur la machine de calcul (2 GPU CUDA) et
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

.PHONY: all setup venv vendor build model corpus test bench bench-infer bench-encoding bench-decision env clean help

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

# Passe avant native en réassociation sûre — OPT-IN, `make build NATIVE_FP=1`.
#
# T21 a mesuré ×4,1 sur la passe avant en autorisant GCC à réassocier les sommes
# (13 143 contre 3 218 éval/s), et a retenu ce sous-ensemble de drapeaux pour le
# build WebAssembly. Mesuré ici en natif : 11 171 contre 2 930 éval/s, ×3,8.
#
# Ce n'est PAS le défaut, et c'est délibéré : T20 chiffre sa parité
# WebAssembly <-> natif contre le natif par défaut. Changer ce défaut
# déplacerait silencieusement la référence d'une mesure déjà publiée par
# l'autre piste. À trancher entre les deux pistes, pas d'un côté seulement.
#
# T11 a été mesuré AVEC ce drapeau ; son rapport le dit.
ifeq ($(NATIVE_FP),1)
VENDOR_CFLAGS := -O3 -std=c11 -Wall -fPIC -fassociative-math -fno-signed-zeros \
                 -fno-trapping-math -fno-math-errno
endif

INCLUDES := -Isrc -I$(REFERENCE)/c_engine -I$(REFERENCE)/c_inference

build: $(LIBRARY)

SOURCES := src/gn_rules_reference.c src/gn_encoding.c src/gn_position_id.c \
           src/gn_rollout.c src/gn_bearoff.c src/gn_evalcache.c \
           src/gn_search.c \
           src/gn_infer_reference.c src/gn_choose.c src/gn_met.c src/gn_cube.c
HEADERS := src/gn_rules.h src/gn_encoding.h src/gn_position_id.h src/gn_infer.h \
           src/gn_rollout.h src/gn_bearoff.h src/gn_evalcache.h \
           src/gn_choose.h src/gn_search.h src/gn_met.h src/gn_met_table.h \
           src/gn_cube.h
OBJECTS := $(patsubst src/%.c,$(BUILD)/%.o,$(SOURCES))

# Sources vendorées, compilées telles quelles — voir VENDOR_CFLAGS.
VENDOR_OBJECTS := $(BUILD)/bg_engine.o $(BUILD)/nn_eval.o

$(BUILD)/%.o: src/%.c $(HEADERS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Le noyau de lot (T35) suit les drapeaux du build : par défaut -O3 strict
# (vectorisation sur la dimension n, légale sans réassociation — bit-identique
# au scalaire par défaut) ; sous NATIVE_FP=1, les mêmes drapeaux de
# réassociation que la passe avant vendor.
BATCH_CFLAGS := $(filter-out -O2,$(CFLAGS)) -O3
ifeq ($(NATIVE_FP),1)
BATCH_CFLAGS += -fassociative-math -fno-signed-zeros -fno-trapping-math -fno-math-errno
endif
# La recherche, et elle seule, sans contraction FMA.
#
# gcc contracte `a*b + c` en un FMA par défaut (-ffp-contract=fast), avec UN
# arrondi au lieu de deux — et il le fait ou non selon la FORME du code autour.
# Mesuré le 2026-08-26 : regrouper les passes d'élagage, à entrées et à ordre
# de sommation identiques, déplaçait l'équité de ~3e-9, et la contraction était
# la seule différence (docs/mesures/2026-08-26-T3A-regroupement.md).
#
# Ce dépôt fait reposer beaucoup sur l'exactitude bit à bit ; la laisser
# dépendre de la forme du code, c'est la perdre au premier refactor, sans un
# signe. Coût mesuré : 1 %.
#
# `gn_search.c` SEULEMENT, et c'est délibéré : appliquer le drapeau à
# l'inférence déplacerait les sorties du réseau, donc l'empreinte d'évaluation
# qui verrouille les journaux T35 (mesuré : 1d92f0d39fb70cb4 → 3f5f3c8a1ffad278).
# Les campagnes closes resteraient lisibles mais plus reprenables, pour un
# bénéfice nul : la divergence n'était pas dans le réseau.
$(BUILD)/gn_search.o: src/gn_search.c $(HEADERS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -ffp-contract=off $(INCLUDES) -c $< -o $@

$(BUILD)/gn_infer_reference.o: src/gn_infer_reference.c $(HEADERS)
	@mkdir -p $(BUILD)
	$(CC) $(BATCH_CFLAGS) $(INCLUDES) -c $< -o $@

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

corpus: corpus-t01 corpus-t12

corpus-t01:
	$(PYTHON) tools/build_corpus_t01.py

corpus-t12:
	$(PYTHON) tools/build_corpus_t12.py

# ── WebAssembly ──────────────────────────────────────────────────────
#
# Emscripten n'est pas toujours dans le PATH : le paquet Arch l'installe sous
# /usr/lib/emscripten sans lien dans /usr/bin. On le cherche avant de renoncer.
EMCC ?= $(firstword $(shell command -v emcc) /usr/lib/emscripten/emcc)

WASM_DIR := wasm
WASM_BUILD := $(BUILD)/wasm

# Cette liste doit suivre $(SOURCES) : `gn_search.c` est le MÊME fichier des
# deux côtés, et la phase 3 lui a donné des dépendances — table de fin de
# partie, cache d'évaluation, videau. Les omettre ici ne produit pas un module
# amputé mais une erreur de lien, ce qui est la bonne façon d'échouer ; c'est
# ainsi que la dérive s'est vue le 2026-08-27, la cible WebAssembly n'ayant
# plus été construite depuis le 2026-08-03.
#
# `gn_bearoff.c` entre dans le module sans sa table : `gn_bearoff_shared()`
# rend NULL tant que rien ne l'a chargée, et la recherche retombe sur le
# réseau. Servir la table à un navigateur est une décision d'artefact — sa
# taille est en jeu — qui appartient à T50, pas à une liste de sources.
WASM_SOURCES := $(WASM_DIR)/gn_wasm.c \
                src/gn_rules_reference.c src/gn_encoding.c \
                src/gn_position_id.c src/gn_infer_reference.c \
                src/gn_bearoff.c src/gn_evalcache.c src/gn_cube.c \
                src/gn_search.c src/gn_met.c src/gn_choose.c \
                $(REFERENCE)/c_engine/bg_engine.c \
                $(REFERENCE)/c_inference/nn_eval.c

# -O3 et non -O2 : c'est un artefact livré à un navigateur, pas un binaire de
# développement, et T21 doit mesurer ce qui serait réellement servi.
#
# MODULARIZE + EXPORT_ES6 : un module ES, chargeable en page, en Web Worker et
# sous Node. Le même artefact sert donc au test de parité et au banc, ce qui
# évite de mesurer un binaire et d'en vérifier un autre.
#
# --pre-js notice.js : la notice MIT vit dans l'artefact lui-même. Un module
# servi à un navigateur est une copie distribuée — BRIEF.md §7.
# Réassociation flottante : ×3,9 sur le débit navigateur, mesuré en T21.
#
# `forward_raw` de nn_eval.c accumule dans une seule variable. L'addition
# flottante n'étant pas associative, le compilateur n'a le droit ni de dérouler
# ni de vectoriser cette boucle : un MAC toutes les ~4 cycles. Lever
# l'interdiction fait passer Chromium de 2 872 à 11 136 évaluations/s.
#
# **Pas `-ffast-math`.** Celui-ci ajoute `-ffinite-math-only`, c'est-à-dire la
# promesse qu'aucun infini n'apparaîtra — or la sigmoïde `1/(1+expf(-x))`
# déborde vers l'infini par conception sur les positions saturées, et il y en a
# dans le corpus. Le sous-ensemble ci-dessous rend 98,7 % du gain sans faire
# cette promesse (13 143 contre 13 314 éval/s en natif).
#
# Prix payé, mesuré : la parité WebAssembly <-> natif n'est plus au bit près
# mais à 4,77e-7 — sous le seuil de 1e-6 de T20. L'ordre des sommes change,
# le résultat pratiquement pas.
FP_RELAXED ?= -fassociative-math -fno-signed-zeros -fno-trapping-math -fno-math-errno

WASM_EXTRA ?= $(FP_RELAXED)
WASM_FLAGS := -O3 -std=c11 $(WASM_EXTRA) $(INCLUDES) \
  -sMODULARIZE=1 -sEXPORT_ES6=1 -sENVIRONMENT=web,worker,node \
  -sALLOW_MEMORY_GROWTH=1 \
  -sSTACK_SIZE=4194304 \
  -sEXPORTED_RUNTIME_METHODS=ccall,cwrap,HEAPF32,HEAPU8,HEAP32,UTF8ToString \
  -sEXPORTED_FUNCTIONS=_malloc,_free,_gnw_load_model,_gnw_free_model,_gnw_is_loaded,_gnw_num_features,_gnw_num_outputs,_gnw_evaluate_features,_gnw_evaluate_batch,_gnw_money_equity,_gnw_has_simd,_gnw_best_play \
  --pre-js $(WASM_DIR)/notice.js

.PHONY: wasm wasm-simd wasm-scalar wasm-parity

wasm: wasm-scalar wasm-simd

wasm-scalar: $(WASM_BUILD)/gammonnet.mjs
wasm-simd: $(WASM_BUILD)/gammonnet-simd.mjs

$(WASM_BUILD)/gammonnet.mjs: $(WASM_SOURCES) $(HEADERS) $(WASM_DIR)/notice.js
	@mkdir -p $(WASM_BUILD)
	$(EMCC) $(WASM_FLAGS) $(WASM_SOURCES) -o $@
	@stat -c '→ scalaire : %s octets  %n' $(WASM_BUILD)/gammonnet.wasm

$(WASM_BUILD)/gammonnet-simd.mjs: $(WASM_SOURCES) $(HEADERS) $(WASM_DIR)/notice.js
	@mkdir -p $(WASM_BUILD)
	$(EMCC) $(WASM_FLAGS) -msimd128 $(WASM_SOURCES) -o $@
	@stat -c '→ SIMD     : %s octets  %n' $(WASM_BUILD)/gammonnet-simd.wasm

# Parité WebAssembly <-> natif, sur le repère figé produit par le côté natif.
wasm-parity: wasm $(MODEL)
	$(PYTHON) tools/dump_reference.py
	node $(WASM_DIR)/parity.mjs

# ── Mesure ───────────────────────────────────────────────────────────

test: build
	$(PYTHON) -m pytest tests/ -q

bench: build
	$(PYTHON) bench/bench_throughput.py

# Le débit d'évaluation du réseau, en C — la ligne de base à laquelle T21
# compare le navigateur. En C et non via ctypes : T05 a mesuré la liaison
# Python à un facteur dix, et une pénalité WebAssembly calculée contre une
# base enveloppée de Python mesurerait ctypes, pas le navigateur.
BENCH_INFER := $(BUILD)/bench_infer

$(BENCH_INFER): bench/bench_infer.c $(OBJECTS) $(VENDOR_OBJECTS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lm

bench-infer: build $(BENCH_INFER) $(MODEL)
	$(PYTHON) tools/dump_reference.py
	$(BENCH_INFER) $(MODEL) $(BUILD)/reference.bin

# T3A branché : ce qu'une évaluation coûte à une RECHERCHE, encodage compris —
# le coût que bench-infer exclut par construction, et qui est le plancher du
# petit réseau.
BENCH_ENCODING := $(BUILD)/bench_encoding
PRUNE_MODEL := models/prune_32.bin

$(BENCH_ENCODING): bench/bench_encoding.c $(OBJECTS) $(VENDOR_OBJECTS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lm

bench-encoding: build $(BENCH_ENCODING) $(MODEL)
	$(BENCH_ENCODING) $(MODEL) $(PRUNE_MODEL)

# Une décision 2-ply, sans Python dans le cadre : ce qu'il faut pour répondre à
# « où passe le temps d'une décision », et ce qui se passe sous callgrind.
BENCH_DECISION := $(BUILD)/bench_decision

$(BENCH_DECISION): bench/bench_decision.c $(OBJECTS) $(VENDOR_OBJECTS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lm

bench-decision: build $(BENCH_DECISION) $(MODEL)
	$(BENCH_DECISION) $(MODEL) 20

clean:
	rm -rf build/
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

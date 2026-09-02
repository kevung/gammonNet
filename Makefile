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
#   make fetch-release  télécharge et vérifie l'artefact float16 épinglé (#18)
#   make serve   démarre le serveur HTTP (mode `serve`, #18)

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

.PHONY: all setup venv vendor build model corpus test bench wasm-api bench-infer bench-encoding bench-decision bench-batch bench-cube bench-sparsity bench-width bench-width-wasm bench-width-wasm-fp tie-census test-tile artifact env clean help

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
           src/gn_notation.c \
           src/gn_rollout.c src/gn_bearoff.c src/gn_evalcache.c \
           src/gn_search.c \
           src/gn_infer_reference.c src/gn_choose.c src/gn_met.c src/gn_cube.c \
           src/gn_gemm_int8.c src/gn_int8_model.c
HEADERS := src/gn_rules.h src/gn_encoding.h src/gn_position_id.h src/gn_infer.h \
           src/gn_notation.h \
           src/gn_rollout.h src/gn_bearoff.h src/gn_evalcache.h \
           src/gn_choose.h src/gn_search.h src/gn_met.h src/gn_met_table.h \
           src/gn_cube.h src/gn_gemm_int8.h src/gn_int8_model.h
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

# Le noyau de lot écrit à la main (T84) — OPT-IN, `make build KERNEL_INTRINSICS=1`.
#
# Mesuré le 2026-09-02 : ×2,17 sur le débit du noyau et ×1,81 sur une décision
# 2-ply k=12, à largeur 32, contre l'auto-vectorisation — et BIT À BIT
# (max|Δ| = 0 aux trois largeurs, `bench/bench_kernel.c` le vérifie avant de
# chronométrer quoi que ce soit). Le gain n'est pas discutable et le résultat
# ne bouge pas d'un bit.
#
# Ce n'est PAS le défaut EN NATIF, et c'est délibéré, pour la même raison que
# NATIVE_FP : le binaire livré cible le x86-64 DE BASE, sans AVX2. Les
# intrinsèques demandent `-march=native` (ou au moins `-mavx`), donc un binaire
# qui ne tournerait plus sur une machine sans AVX2 — ou une répartition à
# l'exécution, qui est un autre chantier. La décision appartient à T50, pas à un
# jeu de drapeaux.
#
# La cible WebAssembly, elle, n'a pas cette contrainte : `gammonnet-simd.wasm`
# assume déjà SIMD128, donc rien à répartir. T91 y a fait des intrinsèques LE
# DÉFAUT — voir `WASM_KERNEL` plus bas, et
# docs/mesures/2026-09-03-T91-wasm-noyau-par-defaut.md.
#
# `-ffp-contract=off` accompagne obligatoirement : sans lui gcc contracte les
# multiplications et additions ÉCRITES SÉPARÉMENT en FMA (un arrondi au lieu de
# deux) et le bit à bit tombe.
KERNEL_ARCH ?= -march=native
ifeq ($(KERNEL_INTRINSICS),1)
BATCH_CFLAGS += -DGN_KERNEL_INTRINSICS -ffp-contract=off $(KERNEL_ARCH)
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
PRUNE_MODEL := models/prune_32.bin

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
                src/gn_position_id.c src/gn_notation.c src/gn_infer_reference.c \
                src/gn_bearoff.c src/gn_evalcache.c src/gn_cube.c \
                src/gn_search.c src/gn_met.c src/gn_choose.c \
                src/gn_gemm_int8.c src/gn_int8_model.c \
                $(REFERENCE)/c_engine/bg_engine.c \
                $(REFERENCE)/c_inference/nn_eval.c

# -O3 et non -O2 : c'est un artefact livré à un navigateur, pas un binaire de
# développement, et T21 doit mesurer ce qui serait réellement servi.
#
# MODULARIZE + EXPORT_ES6 : un module ES, chargeable en page, en Web Worker et
# sous Node. Le même artefact sert donc au test de parité et au banc, ce qui
# évite de mesurer un binaire et d'en vérifier un autre.
#
# --extern-pre-js notice.js : la notice MIT vit dans l'artefact lui-même. Un module
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
#
# ── T91 : CE DRAPEAU N'EST PLUS DANS L'ARTEFACT ─────────────────────
#
# Il y est resté d'août 2026 à ce jour, et T84 a mesuré le 2026-09-02 que la
# configuration livrée était, dans un navigateur, LA PLUS LENTE des six
# qu'elle chronométrait : 12 062 éval/s contre 37 923 au noyau écrit à la main.
# La raison est que le chemin chaud a changé sous le drapeau. T21 l'a adopté
# pour `forward_raw` de `nn_eval.c`, un accumulateur scalaire que la
# réassociation libère ; depuis T35 une décision passe par le noyau PAR LOT de
# `gn_infer_reference.c`, où la réassociation ne libère rien et gêne
# l'auto-vectorisation — 27 890 → 9 905 éval/s à largeur 16.
#
# Mesuré ici, avec le noyau écrit à la main (Node/V8, 2026-09-02, largeur 16) :
# 45 666 éval/s sans le drapeau, 48 046 avec — et une décision à 0,3309 s
# contre 0,3021 s. Il ne rend donc plus qu'environ 8 % là où il en coûtait 280,
# parce que les intrinsèques ne lui laissent plus rien à réassocier dans le
# noyau.
#
# Et il coûte deux exactitudes, l'une et l'autre mesurées :
#   — le noyau par lot n'est plus bit à bit contre le chemin scalaire du MÊME
#     artefact (max|Δ| = 3,3e-07), parce que c'est la RÉFÉRENCE qui bouge ;
#   — la parité WebAssembly <-> natif reste à 6,4e-07 au lieu de tomber à zéro.
#
# Huit pour cent contre le bit à bit : c'est le bit à bit qui gagne. Le drapeau
# reste défini — `make wasm WASM_EXTRA="$(FP_RELAXED)"` le rend, et
# `bench-width-wasm-fp` le mesure — mais il n'est plus le défaut.
FP_RELAXED ?= -fassociative-math -fno-signed-zeros -fno-trapping-math -fno-math-errno

# Le noyau écrit à la main (T84) est le DÉFAUT de la cible WebAssembly, et il
# l'est SANS CONDITION là où le natif ne peut pas : `gammonnet-simd.wasm`
# assume déjà SIMD128, donc il n'y a pas de répartition à l'exécution à écrire.
# La construction scalaire prend la même définition et retombe sur la variante
# scalaire du noyau (`GN_VEC_LANES 1`), qui est bit à bit elle aussi.
#
# `-ffp-contract=off` accompagne obligatoirement : sans lui le compilateur est
# libre de contracter en FMA des multiplications et des additions écrites
# séparément — un arrondi au lieu de deux — et le bit à bit tombe. WebAssembly
# n'a pas de FMA hors `relaxed-simd`, mais le drapeau ne coûte rien et la
# garantie ne doit pas dépendre d'une extension que le module n'active pas.
WASM_KERNEL ?= -DGN_KERNEL_INTRINSICS -ffp-contract=off

# La largeur de lot de la cible WebAssembly, tranchée SÉPARÉMENT du natif.
#
# T84 a clos la question en natif (largeur 32 conservée : passer à 16 n'y rend
# que 6,9 %), mais son sixième écart — Chromium, 32 → 16, −11,6 % — était le
# seul à dépasser le seuil, et il portait sur cette cible-ci. Remesuré ici sur
# le noyau écrit à la main, l'écart est plus grand encore que ce que T84 lisait.
# SIMD128 n'a que quatre voies : à largeur 32 la tuile dégénère en 1 ligne × 8
# vecteurs (une seule chaîne d'accumulation par ligne), à largeur 16 elle vaut
# 2 lignes × 4 vecteurs — deux chaînes indépendantes, et c'est là tout l'objet
# du noyau.
#
# Le regroupement des 21 lancers reste, et n'a jamais été en cause : un lot de
# 16 se remplit à 96,5 % PARCE QU'il est groupé ; dégroupé il retomberait vers
# les 84 % que le portage Go mesure.
WASM_BATCH ?= -DGN_EVAL_BATCH=16

WASM_EXTRA ?=
WASM_CFLAGS := -O3 -std=c11 $(WASM_KERNEL) $(WASM_BATCH) $(WASM_EXTRA) $(INCLUDES)
WASM_FLAGS := $(WASM_CFLAGS) \
  -sMODULARIZE=1 -sEXPORT_ES6=1 -sENVIRONMENT=web,worker,node \
  -sALLOW_MEMORY_GROWTH=1 \
  -sSTACK_SIZE=4194304 \
  -sEXPORTED_RUNTIME_METHODS=ccall,cwrap,HEAPF32,HEAPF64,HEAP8,HEAPU8,HEAP32,UTF8ToString \
  -sEXPORTED_FUNCTIONS=_malloc,_free,_gnw_load_model,_gnw_free_model,_gnw_is_loaded,_gnw_num_features,_gnw_num_outputs,_gnw_evaluate_features,_gnw_evaluate_batch,_gnw_money_equity,_gnw_has_simd,_gnw_best_play,_gnw_load_prune,_gnw_prune_k,_gnw_rank_plays,_gnw_cube_decide,_gnw_load_bearoff,_gnw_enable_cache,_gnw_gemm_int8_relu,_gnw_gemm_int8_raw,_gnw_position_encode,_gnw_position_decode,_gnw_xgid_encode,_gnw_xgid_decode,_gnw_pip_count \
  --extern-pre-js $(WASM_DIR)/notice.js

.PHONY: wasm wasm-simd wasm-scalar wasm-parity wasm-parity-int8 wasm-codec

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

# Les invariants de l'API JavaScript. La parité vérifie que le module CALCULE
# comme le natif ; ceci vérifie qu'il RÉPOND ce qu'il promet — le classement des
# N meilleurs coups, notamment, où deux défauts silencieux ont été trouvés.
#
# Deux surfaces, deux fichiers. `api_invariants` interroge le module ;
# `worker_invariants` interroge le PROTOCOLE DE WORKER, qui est la surface que
# le navigateur voit réellement et qui, faute d'être testée, a laissé trois
# points d'entrée exportés rester inatteignables (T86).
wasm-api: wasm $(MODEL) $(PRUNE_MODEL)
	node $(WASM_DIR)/api_invariants.mjs
	node $(WASM_DIR)/worker_invariants.mjs
	node $(WASM_DIR)/pool_invariants.mjs

# La parité du CODEC, sur le corpus T12 entier et à l'égalité EXACTE — un
# identifiant est une chaîne, il n'y a pas de tolérance à lui accorder. Le
# repère vient du C natif (`tools/dump_codec_reference.py`), jamais de
# l'écriture JavaScript que ces exports remplacent : la vérifier contre elle
# serait circulaire, puisqu'elle a été validée contre ce module.
.PHONY: wasm-codec
wasm-codec: wasm build
	$(PYTHON) tools/dump_codec_reference.py
	node $(WASM_DIR)/codec_parity.mjs

DUMP_INT8 := $(BUILD)/dump_reference_int8
$(DUMP_INT8): tools/dump_reference_int8.c src/gn_gemm_int8.c $(HEADERS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -Isrc -o $@ tools/dump_reference_int8.c src/gn_gemm_int8.c src/gn_int8_model.c -lm

# Parité du chemin int8 DÉTERMINISTE (gn_gemm_int8) : le repère est produit par
# le noyau natif dispatché sur cette machine (scalaire/SSE2/AVX2), rejoué au
# bit près -- pas à une tolérance -- par les deux builds WebAssembly.
wasm-parity-int8: wasm $(DUMP_INT8)
	$(DUMP_INT8)
	node $(WASM_DIR)/parity_int8.mjs

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

$(BENCH_ENCODING): bench/bench_encoding.c $(OBJECTS) $(VENDOR_OBJECTS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lm

# T50 : l'artefact publiable. Refuse de se déclarer complet s'il manque une
# pièce — notamment le WebAssembly, qui demande Emscripten.
.PHONY: artifact
artifact: build wasm
	$(PYTHON) tools/package_artifact.py --version $(VERSION)

VERSION ?= v1

bench-encoding: build $(BENCH_ENCODING) $(MODEL)
	$(BENCH_ENCODING) $(MODEL) $(PRUNE_MODEL)

# Une décision 2-ply, sans Python dans le cadre : ce qu'il faut pour répondre à
# « où passe le temps d'une décision », et ce qui se passe sous callgrind.
# T73 -- int8 contre f32 sur les formes du réseau. La cible `bench-gemm-sse2`
# recompile le même programme sans FMA ni AVX2 : c'est le test décisif de
# l'anomalie du lot (x2,21 en Wasm contre x8,5 en natif, T21).
BENCH_GEMM := $(BUILD)/bench_gemm_int8

$(BENCH_GEMM): bench/bench_gemm_int8.c src/gn_gemm_int8.c $(HEADERS)
	$(CC) $(CFLAGS) -Isrc -o $@ bench/bench_gemm_int8.c src/gn_gemm_int8.c -lm

bench-gemm: $(BENCH_GEMM)
	$(BENCH_GEMM) 2000 --json docs/mesures/t73-gemm-int8.json

$(BUILD)/bench_gemm_int8_sse2: bench/bench_gemm_int8.c src/gn_gemm_int8.c $(HEADERS)
	$(CC) $(CFLAGS) -mno-fma -mno-avx2 -msse2 -Isrc -o $@ \
	      bench/bench_gemm_int8.c src/gn_gemm_int8.c -lm

bench-gemm-sse2: $(BUILD)/bench_gemm_int8_sse2
	$(BUILD)/bench_gemm_int8_sse2 2000 --json docs/mesures/t73-gemm-int8-sse2.json

# ── Le census des ex æquo (T88) ──────────────────────────────────────
#
# Combien de fois deux coups candidats portent-ils EXACTEMENT la même équité ?
# Tant que la réponse n'est pas mesurée, « le classement n'est pas
# déterministe » reste une lecture de code — ce que la règle 3 de CLAUDE.md
# interdit de transformer en conclusion.
#
# Le binaire est compilé À PART, avec -DGN_TIE_CENSUS, parce que les compteurs
# n'ont rien à faire dans la bibliothèque livrée. `gn_search.c` garde son
# -ffp-contract=off : sans lui, ce banc mesurerait les ex æquo d'un AUTRE
# moteur que celui qui est livré.
#
#   make tie-census                 ply 0, tout le corpus T12, 21 lancers
#   make tie-census PLY=2 K=12 N=60 la forme canonique, sur 60 positions
#
# `--dump` (TIE_DUMP=1) écrit le classement lui-même sur la sortie standard :
# c'est le seul moyen de VOIR une permutation, les équités étant par
# définition identiques.
TIE_CENSUS := $(BUILD)/tie_census
TIE_SOURCES := $(filter-out src/gn_search.c,$(SOURCES))
PLY ?= 0
K ?= 0
N ?= 0
CORPUS ?= tests/data/corpus_t12.jsonl

$(TIE_CENSUS): bench/tie_census.c $(TIE_SOURCES) src/gn_search.c $(HEADERS) \
               $(REFERENCE)/c_engine/bg_engine.c $(REFERENCE)/c_inference/nn_eval.c
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -ffp-contract=off -DGN_TIE_CENSUS $(INCLUDES) \
	      -c src/gn_search.c -o $(BUILD)/gn_search_census.o
	$(CC) $(VENDOR_CFLAGS) $(INCLUDES) -c $(REFERENCE)/c_engine/bg_engine.c \
	      -o $(BUILD)/bg_engine_census.o
	$(CC) $(VENDOR_CFLAGS) $(INCLUDES) -c $(REFERENCE)/c_inference/nn_eval.c \
	      -o $(BUILD)/nn_eval_census.o
	$(CC) $(CFLAGS) -DGN_TIE_CENSUS $(INCLUDES) -o $@ \
	      bench/tie_census.c $(TIE_SOURCES) $(BUILD)/gn_search_census.o \
	      $(BUILD)/bg_engine_census.o $(BUILD)/nn_eval_census.o -lm

tie-census: $(TIE_CENSUS) $(MODEL)
	$(TIE_CENSUS) $(MODEL) $(CORPUS) $(PLY) \
	    $(if $(filter-out 0,$(K)),$(PRUNE_MODEL),-) $(K) $(N) \
	    $(if $(filter-out 0,$(TIE_DUMP)),--dump,)

BENCH_DECISION := $(BUILD)/bench_decision

$(BENCH_DECISION): bench/bench_decision.c $(OBJECTS) $(VENDOR_OBJECTS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lm

bench-decision: build $(BENCH_DECISION) $(MODEL)
	$(BENCH_DECISION) $(MODEL) 20

# Le gain de lot, largeur par largeur. Ce banc existait sans règle pour le
# construire ; il se compilait à la main, donc au hasard des drapeaux — et
# l'écart entre -O2 et -O3 y vaut 48 % (mesuré le 2026-09-02). La règle fixe
# -O3, comme BATCH_CFLAGS le fait pour le noyau livré.
#
# ATTENTION à ce qu'il mesure : sa largeur de lot est une VARIABLE d'exécution
# et il n'a pas la sparsité de la couche 1. Sa courbe n'est donc PAS celle du
# noyau livré, dont la largeur est une constante de compilation. Il répond à
# « le lot rend-il, et reste-t-il bit à bit », pas à « quelle largeur choisir ».
BENCH_BATCH := $(BUILD)/bench_batch

$(BENCH_BATCH): bench/bench_batch.c $(OBJECTS) $(VENDOR_OBJECTS)
	@mkdir -p $(BUILD)
	$(CC) $(filter-out -O2,$(CFLAGS)) -O3 $(INCLUDES) -o $@ $^ -lm

bench-batch: build $(BENCH_BATCH) $(MODEL)
	$(PYTHON) tools/dump_reference.py
	$(BENCH_BATCH) $(MODEL) $(BUILD)/reference.bin

# Ce que le videau coûte, money et au score. `gn_cube_value` est appelé une fois
# par nœud évalué sous `use_cube` (gn_search.c:289) : au score il pèse deux
# ordres de grandeur de plus qu'en money, et c'est ce que ce banc établit.
BENCH_CUBE := $(BUILD)/bench_cube

$(BENCH_CUBE): bench/bench_cube.c $(OBJECTS) $(VENDOR_OBJECTS)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lm

bench-cube: build $(BENCH_CUBE) $(MODEL)
	$(PYTHON) tools/dump_reference.py
	$(BENCH_CUBE) $(MODEL) $(BUILD)/reference.bin

# ── T84 : la largeur de lot, tranchée par des intrinsèques ───────────
#
# La question n'est pas « 8 ou 32 » : c'est *le regroupement des 21 lancers
# gagne-t-il encore sa complexité si le noyau est écrit à la main ?*
#
# Tout balayage précédent a mesuré autre chose. T3A l'avait nommé : gcc ne
# vectorise la boucle chaude qu'à partir de 24, donc tester une largeur de 8
# sans intrinsèques revient à tomber de la falaise. Et `bench_batch.c` prend sa
# largeur en VARIABLE d'exécution, donc sa courbe est la sienne, pas celle du
# noyau livré.
#
# `make bench-width` construit NEUF binaires — trois largeurs × trois noyaux —
# et les fait tourner l'un après l'autre. Les trois noyaux :
#
#   auto        ce qui est livré : auto-vectorisé, cible x86-64 de base (SSE)
#   auto-avx2   auto-vectorisé, -march=native (AVX2) — la MÊME source
#   intrin      les intrinsèques de src/gn_kernel_f32.h, -march=native
#
# Les deux dernières colonnes séparent « écrit à la main » de « jeu
# d'instructions plus large », que le premier chiffre venu confondrait.
#
# -ffp-contract=off partout où -march=native entre : sans lui gcc contracte en
# FMA (un arrondi au lieu de deux) et le bit à bit tombe — y compris sur des
# intrinsèques écrites explicitement. Les sources VENDORÉES restent à -O2 de
# base dans les neuf cas : elles sont la RÉFÉRENCE scalaire, elle ne doit pas
# bouger d'un binaire à l'autre.
KERNEL_WIDTHS ?= 8 16 32
KERNEL_REPS ?= 5
KERNEL_PASSES ?= 3
KERNEL_DECISIONS ?= 10

KERNEL_BASE_FLAGS := -std=c11 -Wall -Wextra -O3 -ffp-contract=off

# $(1) nom, $(2) drapeaux supplémentaires, $(3) largeur
define KERNEL_BUILD
	@mkdir -p $(BUILD)/kernel
	$(CC) $(KERNEL_BASE_FLAGS) $(2) -DGN_EVAL_BATCH=$(3) -fopt-info-vec \
	      $(INCLUDES) -c src/gn_infer_reference.c \
	      -o $(BUILD)/kernel/infer_$(1)_$(3).o 2> $(BUILD)/kernel/vec_$(1)_$(3).log
	$(CC) $(KERNEL_BASE_FLAGS) $(2) -DGN_EVAL_BATCH=$(3) -ffp-contract=off \
	      $(INCLUDES) -c src/gn_search.c -o $(BUILD)/kernel/search_$(1)_$(3).o
	$(CC) $(CFLAGS) -DGN_EVAL_BATCH=$(3) $(2) $(INCLUDES) -o $(BUILD)/kernel/bench_$(1)_$(3) \
	      bench/bench_kernel.c \
	      $(filter-out src/gn_infer_reference.c src/gn_search.c,$(SOURCES)) \
	      $(BUILD)/kernel/infer_$(1)_$(3).o $(BUILD)/kernel/search_$(1)_$(3).o \
	      $(BUILD)/bg_engine.o $(BUILD)/nn_eval.o -lm
endef

.PHONY: bench-width
bench-width: build $(MODEL) $(PRUNE_MODEL)
	@for w in $(KERNEL_WIDTHS); do \
	    $(MAKE) --no-print-directory kernel-variants WIDTH=$$w; \
	done
	$(PYTHON) bench/width_sweep.py --passes $(KERNEL_PASSES) \
	    --reps $(KERNEL_REPS) --decisions $(KERNEL_DECISIONS) \
	    --json docs/mesures/t84-largeur-noyau.json

.PHONY: kernel-variants
kernel-variants:
	$(call KERNEL_BUILD,auto,,$(WIDTH))
	$(call KERNEL_BUILD,auto-avx2,-march=native,$(WIDTH))
	$(call KERNEL_BUILD,intrin,-march=native -DGN_KERNEL_INTRINSICS,$(WIDTH))

# Le remplissage des voies par largeur — la preuve directe sur le REGROUPEMENT,
# et non sur la vitesse. Un binaire à part : les compteurs n'ont rien à faire
# dans celui qu'on chronomètre.
.PHONY: bench-width-fill
bench-width-fill: build $(MODEL) $(PRUNE_MODEL)
	@for w in $(KERNEL_WIDTHS); do \
	    $(MAKE) --no-print-directory kernel-fill WIDTH=$$w; \
	    $(BUILD)/kernel/bench_fill_$$w $(MODEL) $(PRUNE_MODEL) 1 8 \
	        | grep -E "largeur|remplissage|  (grand|petit) "; \
	done

.PHONY: kernel-fill
kernel-fill:
	$(call KERNEL_BUILD,fill,-march=native -DGN_KERNEL_INTRINSICS -DGN_BATCH_FILL_STATS,$(WIDTH))

# ── T84, volet navigateur : le même banc, compilé en WebAssembly ─────
#
# L'enjeu y est plus grand qu'en natif : SIMD128 n'a que QUATRE voies
# flottantes, donc une largeur de 8 y tient en deux vecteurs et le noyau
# écrit à la main a moins de marge. Le même `bench/bench_kernel.c`, les mêmes
# largeurs, les deux noyaux.
#
# PAS de `-fassociative-math` ici : la réassociation change l'ordre des sommes,
# donc le `max|Δ| = 0` que ce banc vérifie n'aurait plus de sens. Ce que ce
# volet mesure est le noyau, à arithmétique fixée — ce qui est aussi, depuis
# T91, l'arithmétique de l'artefact livré. `bench-width-wasm-fp` construit les
# variantes qui rendent le drapeau, pour pouvoir le mesurer.
WASM_KERNEL_CFLAGS := -O3 -std=c11 -msimd128 -ffp-contract=off $(INCLUDES)
WASM_KERNEL_LDFLAGS := -sENVIRONMENT=node,web -sALLOW_MEMORY_GROWTH=1 \
  -sSTACK_SIZE=4194304 --preload-file models@models
WASM_KERNEL_FLAGS := $(WASM_KERNEL_CFLAGS) $(WASM_KERNEL_LDFLAGS)

WASM_KERNEL_SOURCES := bench/bench_kernel.c \
  src/gn_rules_reference.c src/gn_encoding.c src/gn_position_id.c \
  src/gn_infer_reference.c src/gn_bearoff.c src/gn_evalcache.c src/gn_cube.c \
  src/gn_search.c src/gn_met.c src/gn_choose.c src/gn_gemm_int8.c \
  src/gn_int8_model.c src/gn_rollout.c \
  $(REFERENCE)/c_engine/bg_engine.c $(REFERENCE)/c_inference/nn_eval.c

.PHONY: bench-width-wasm wasm-kernel-variants
wasm-kernel-variants:
	@mkdir -p $(BUILD)/wasm
	$(EMCC) $(WASM_KERNEL_FLAGS) -DGN_EVAL_BATCH=$(WIDTH) $(WASM_KERNEL_SOURCES) \
	    -o $(BUILD)/wasm/bench_kernel_auto_$(WIDTH).js
	$(EMCC) $(WASM_KERNEL_FLAGS) -DGN_EVAL_BATCH=$(WIDTH) -DGN_KERNEL_INTRINSICS \
	    $(WASM_KERNEL_SOURCES) -o $(BUILD)/wasm/bench_kernel_intrin_$(WIDTH).js

bench-width-wasm: $(MODEL) $(PRUNE_MODEL)
	@for w in $(KERNEL_WIDTHS); do \
	    $(MAKE) --no-print-directory wasm-kernel-variants WIDTH=$$w; \
	done
	$(PYTHON) bench/width_sweep.py --target wasm --passes $(KERNEL_PASSES) \
	    --reps $(WASM_KERNEL_REPS) --decisions $(WASM_KERNEL_DECISIONS) \
	    --json docs/mesures/t84-largeur-noyau-wasm.json

WASM_KERNEL_REPS ?= 3
WASM_KERNEL_DECISIONS ?= 3

# ── T91, volet drapeaux : le MÊME banc, aux drapeaux de l'ARTEFACT ───
#
# Ce que les deux variantes ci-dessus mesurent est le NOYAU, à arithmétique
# fixée — délibérément, pour que le `max|Δ| = 0` ait un sens. Ce que
# l'utilisateur exécute est autre chose : `gammonnet-simd.wasm` porte
# `$(FP_RELAXED)`, et T84 a mesuré que la réassociation COÛTE un facteur 2,8
# sur le chemin par lot alors qu'elle achète ×3,9 sur la passe avant scalaire.
# Les deux chiffres sont vrais et ils portent sur DEUX unités de compilation
# différentes : `nn_eval.c` (la passe avant vendorée, un accumulateur scalaire
# que la réassociation libère) et `gn_infer_reference.c` (le noyau par lot, que
# la réassociation ABÎME et dont elle fait tomber le bit à bit).
#
# D'où trois variantes de plus, qui rendent la table « drapeaux de l'artefact »
# de T84 reproductible et lui ajoutent la seule combinaison qu'elle n'avait pas
# essayée :
#
#   autofp        auto-vectorisé + $(FP_RELAXED) partout — L'ARTEFACT D'AVANT
#   intrinfp      intrinsèques   + $(FP_RELAXED) partout
#   intrinsplit   intrinsèques, $(FP_RELAXED) sur `nn_eval.c` SEULEMENT
#
# `intrinsplit` est la configuration livrée : elle garde le ×3,9 de T21 là où
# il a été mesuré et rend au noyau par lot son arithmétique — donc son bit à
# bit, que ce banc vérifie avant de chronométrer quoi que ce soit.
WASM_KERNEL_NOFP := $(filter-out $(REFERENCE)/c_inference/nn_eval.c,$(WASM_KERNEL_SOURCES))

# $(1) nom, $(2) drapeaux du noyau, $(3) largeur
define WASM_KERNEL_SPLIT_BUILD
	@mkdir -p $(BUILD)/wasm
	$(EMCC) $(WASM_KERNEL_CFLAGS) $(FP_RELAXED) -c \
	    $(REFERENCE)/c_inference/nn_eval.c -o $(BUILD)/wasm/nn_eval_relaxed.o
	$(EMCC) $(WASM_KERNEL_FLAGS) $(2) -DGN_EVAL_BATCH=$(3) \
	    $(WASM_KERNEL_NOFP) $(BUILD)/wasm/nn_eval_relaxed.o \
	    -o $(BUILD)/wasm/bench_kernel_$(1)_$(3).js
endef

.PHONY: wasm-kernel-fp-variants
wasm-kernel-fp-variants:
	@mkdir -p $(BUILD)/wasm
	$(EMCC) $(WASM_KERNEL_FLAGS) $(FP_RELAXED) -DGN_EVAL_BATCH=$(WIDTH) \
	    $(WASM_KERNEL_SOURCES) -o $(BUILD)/wasm/bench_kernel_autofp_$(WIDTH).js
	$(EMCC) $(WASM_KERNEL_FLAGS) $(FP_RELAXED) -DGN_EVAL_BATCH=$(WIDTH) \
	    -DGN_KERNEL_INTRINSICS $(WASM_KERNEL_SOURCES) \
	    -o $(BUILD)/wasm/bench_kernel_intrinfp_$(WIDTH).js
	$(call WASM_KERNEL_SPLIT_BUILD,intrinsplit,-DGN_KERNEL_INTRINSICS,$(WIDTH))

# Les cinq variantes, aux largeurs demandées, prêtes pour
# `node bench/browser_kernel.mjs --kernels autofp,intrinfp,intrinsplit`.
.PHONY: bench-width-wasm-fp
bench-width-wasm-fp: $(MODEL) $(PRUNE_MODEL)
	@for w in $(WASM_FP_WIDTHS); do \
	    $(MAKE) --no-print-directory wasm-kernel-fp-variants WIDTH=$$w; \
	done

WASM_FP_WIDTHS ?= 16 32

# ── T89 : la sparsité, par réseau et par type de lot ─────────────────
#
# La sparsité de la couche 1 est livrée depuis le 2026-08-26 et vaut ×1,16 —
# mais c'est le chiffre des DEUX réseaux ensemble, et le registre attend 78 %
# sur le PETIT seul. Personne n'a séparé les deux.
#
# Deux choses que ce banc fait et qu'aucun autre ne fait :
#   — il éteint la sparsité RÉSEAU PAR RÉSEAU (`-DGN_BATCH_SPARSITY_SWITCH`,
#     compilé hors de la bibliothèque livrée : la sparsité n'est pas une option
#     d'exécution, c'est le noyau) ;
#   — il distingue un lot FRATRIE (les coups légaux d'un plateau et d'un lancer,
#     ce que la recherche donne réellement au noyau) d'un lot de positions
#     QUELCONQUES (ce que `bench_batch.c` mesure sans le dire). L'union des
#     entrées actives n'a pas la même largeur dans les deux cas, et le portage
#     Go a mesuré une PERTE de 9 % sur le second.
BENCH_SPARSITY := $(BUILD)/bench_sparsity
SPARSITY_SOURCES := $(filter-out src/gn_infer_reference.c,$(SOURCES))

$(BENCH_SPARSITY): bench/bench_sparsity.c $(SOURCES) $(HEADERS) \
                   $(REFERENCE)/c_engine/bg_engine.c $(REFERENCE)/c_inference/nn_eval.c
	@mkdir -p $(BUILD)
	$(CC) $(BATCH_CFLAGS) -DGN_BATCH_SPARSITY_SWITCH $(INCLUDES) \
	      -c src/gn_infer_reference.c -o $(BUILD)/gn_infer_sparsity.o
	$(CC) $(CFLAGS) -ffp-contract=off $(INCLUDES) \
	      -c src/gn_search.c -o $(BUILD)/gn_search_sparsity.o
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ bench/bench_sparsity.c \
	      $(filter-out src/gn_infer_reference.c src/gn_search.c,$(SOURCES)) \
	      $(BUILD)/gn_infer_sparsity.o $(BUILD)/gn_search_sparsity.o \
	      $(BUILD)/bg_engine.o $(BUILD)/nn_eval.o -lm

REPS ?= 7
DECISIONS ?= 12

bench-sparsity: build $(BENCH_SPARSITY) $(MODEL) $(PRUNE_MODEL)
	$(BENCH_SPARSITY) $(MODEL) $(PRUNE_MODEL) $(REPS) $(DECISIONS)

# ── T90 : l'arrondi des tuiles, sous ASan ────────────────────────────
#
# Zéro gain. Un garde-fou posé AVANT que T84 déplace ce qu'il garde : le jour
# où une largeur ou une tuile cesse d'être une puissance de deux, `n & ~(t-1)`
# rend une valeur qui n'est PAS un multiple de la tuile, et la boucle lit hors
# de la matrice. Le portage Go a livré exactement cette ligne.
#
# Compilé À PART, avec -fsanitize=address : le débordement est de trois
# flottants au bout d'une ligne, donc invisible sans redzone.
TILE_ASAN := $(BUILD)/tile_asan
ASAN_FLAGS ?= -fsanitize=address,undefined -fno-omit-frame-pointer -g

$(TILE_ASAN): tests/tile_asan.c src/gn_tile.h
	@mkdir -p $(BUILD)
	$(CC) -O1 -std=c11 -Wall -Wextra $(ASAN_FLAGS) -Isrc -o $@ tests/tile_asan.c

.PHONY: test-tile
test-tile: $(TILE_ASAN)
	$(TILE_ASAN)
	@# Le volet NÉGATIF : la forme masquée doit mourir. Si elle survit, ce
	@# n'est pas que le code est sain, c'est qu'ASan ne tourne pas.
	@if $(TILE_ASAN) --trap >/dev/null 2>&1; then \
	    echo "ÉCHEC : la forme masquée n'a pas débordé — ASan est-il actif ?"; \
	    exit 1; \
	else \
	    echo "  --trap : la forme masquée meurt bien sur un débordement de tas"; \
	fi

# ── Serveur HTTP (#18) ───────────────────────────────────────────────

.PHONY: fetch-release serve

# Télécharge et vérifie l'artefact float16 épinglé (models/release_pin.json)
# — le même que la cible WebAssembly. N'a besoin ni de PyTorch ni de gnubg-nn :
# stdlib seule, donc le Python système suffit si le venv n'existe pas encore.
fetch-release:
	$(PYTHON) tools/fetch_release.py

# `make build` d'abord : le serveur charge build/libgammonnet.so.
serve: build fetch-release
	$(PYTHON) tools/serve.py

clean:
	rm -rf build/
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

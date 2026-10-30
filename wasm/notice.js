/*
 * gammonNet — évaluateur de positions de backgammon
 *
 * Ce module WebAssembly est une copie distribuée. Les notices ci-dessous
 * voyagent donc avec lui, comme la licence MIT l'exige pour « all copies or
 * substantial portions of the Software ». L'inventaire complet, avec ce qui est
 * effectivement utilisé de chaque brique, est dans THIRD-PARTY.md.
 *
 * ── Poids du réseau et moteur d'inférence ───────────────────────────────
 * backgammon-ai-engine — Copyright (c) 2026 Alex Strehl — licence MIT
 * (poids, commit 18b0a80 ; les sources compilées, commit 7184e2f, portent
 * « Copyright (c) 2026 alexstrehl », le même auteur)
 * https://github.com/alexstrehl/backgammon-ai-engine
 * Réseau : cubeless_prob5_768_768_256_256_256
 *
 * ── gammonNet ──────────────────────────────────────────────────────────
 * Copyright (c) 2026 Kévin Unger — licence MIT
 * https://github.com/kevung/gammonNet
 *
 * ── Ce qui N'EST PAS utilisé ici ───────────────────────────────────────
 * Aucun poids de GNU Backgammon (GPL-3) n'entre dans cet artefact, ni aucun
 * réseau portant une clause non commerciale. Le réseau embarqué est celui
 * d'Alexander Strehl, cité ci-dessus.
 *
 * SPDX-License-Identifier: MIT
 */

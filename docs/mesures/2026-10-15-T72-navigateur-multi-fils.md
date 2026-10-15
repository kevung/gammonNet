# 2026-10-15 — La recherche multi-fils dans un vrai navigateur

**Nature** : une **mesure**, et une seule cible. Firefox 140.17.0esr sans interface, mochy
(16 cœurs / 32 fils, `hardwareConcurrency` 32), page isolée (`crossOriginIsolated` vrai,
en-têtes COOP/COEP du banc). Module `gammonnet-simd-mt` à `9549f92`, réseau
`cubeless_prob5_512_512_256_256`, élagueur `prune_32` à `k=12`, niveau `normal` (2-ply).

**Charge pendant la mesure** : rien de ce dépôt ne tournait ; un démon étranger au dépôt tenait
~2,9 fils, surtout en temps système (`top` : 90 % d'inactivité). Les trois passes ont été
lancées **l'une après l'autre**, jamais en parallèle.

**Banc** : `node bench/browser_threads.mjs --browser firefox --threads 1,2,4,8,16 --decisions 20`.
Les 20 décisions sont une marche fixe (auto-jeu 0-ply, dés d'un générateur congruentiel
figé, `wasm/threads_bench_worker.mjs`) ; ce ne sont **pas** les 20 décisions du banc natif
de `2026-10-13-profil-decision-niveaux.md`, et les deux tableaux ne se divisent pas l'un par
l'autre. Journaux bruts : `t72-navigateur/pass{1,2,3}.log`.

## Résultat

| Fils | s/décision, médiane de 3 | min ; max | Gain |
|---|---|---|---|
| 1 | **2,1128** | 2,1115 ; 2,1151 | ×1,00 |
| 2 | **1,0685** | 1,0678 ; 1,0758 | ×1,98 |
| 4 | **0,5482** | 0,5468 ; 0,5483 | ×3,86 |
| 8 | **0,2831** | 0,2820 ; 0,2832 | ×7,47 |
| 16 | **0,1699** | 0,1683 ; 0,1712 | ×12,43 |

Classements **identiques au mono-fil** à chaque nombre de fils, à chaque passe (le banc
compare au bit).

## Ce que ça dit, et ce que ça ne dit pas

- Le gain est quasi linéaire jusqu'à 8 fils et reste net à 16 : sur ce poste, le défaut
  « fils annoncés, plafonnés à 16 » (`Evaluator.suggestedThreads`) est justifié **par la
  mesure**.
- **Non mesuré** : Chromium (non installé sur les deux machines), un portable à cœurs
  hétérogènes, un téléphone. `hardwareConcurrency` compte des fils logiques ; au-delà des
  cœurs physiques le gain par fil baisse, de combien sur un autre appareil n'est pas connu.
- **Non mesuré** : le coût mémoire du pool de pthreads (créé au démarrage, à la taille des
  fils annoncés plafonnée à 16) sur un appareil contraint.

## Le défaut qui en découle

- Un worker initialisé sur le module multi-fils sans `threads` prend
  `Evaluator.suggestedThreads()` ; le module série reste à un fil.
- Un `EvaluatorPool` de plusieurs workers reste à **un** fil par worker sauf `threads`
  explicite : il parallélise déjà par worker.
- L'artefact embarque désormais `gammonnet-simd-mt.mjs` / `.wasm` (`manifest.json` :
  `wasm_threads`) ; son `QUICKSTART.md` décrit les trois conditions (page isolée, module
  multi-fils, Web Worker).

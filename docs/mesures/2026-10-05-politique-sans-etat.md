# La politique sans état — identité avec T35, parité des cibles, match contre gnubg

> Spécification : `docs/specs/politique-spec.md`. Mesures du 2026-10-05, poste de développement
> (16 fils, chargé par d'autres travaux pendant la mesure).

## 1. Ce qui est mesuré, et ce qui ne l'est pas encore

| Question | Statut |
|---|---|
| La composition reproduit-elle exactement le joueur de T35 ? | **mesuré** (§2) |
| La cible WebAssembly répond-elle comme le natif ? | **mesuré** (§3) |
| La lecture exacte de la défaite certaine coûte-t-elle ? | **mesuré** (§4) |
| Le niveau `normal` en match contre gnubg retrouve-t-il T35 ? | **mesuré** à 2 000 paires (§5), à ±1,1 point |

## 2. Identité avec le joueur de T35

Protocole (`tests/test_policy.py`) : chaque question que la boucle cubeful pose est posée aux
deux joueurs — la politique à une forme explicite (`gn_policy_decide_level`) et
`GammonNetCubePlayer` au même réglage, sans table bilatérale — et leurs réponses comparées.

- **0-ply** : 4 parties money + 4 matchs dupliqués, plus de 500 décisions — **identiques** ; 12
  paires dupliquées politique contre joueur T35 (6 money, 6 match) totalisent **exactement 0**.
- **Réglage de T35** (2-ply, filtre `(0,1,3)`, élagage 12, `GN_POLICY_SLOW=1`) : un match
  dupliqué 3-away/4-away — **identique**, à **une** exception près, celle que la spec §5.2
  prévoit : un double optionnel (bearoff gagné à coup sûr, 3-away/4-away, videau 2 possédé ;
  ne pas doubler = doubler = 0,81436 de MWC) que T35 double et que la politique ne double pas.
  Sans coût d'équité, par définition.

La composition ne change donc rien à ce que T35 a mesuré, sauf ce double sans valeur.

## 3. Parité WebAssembly ↔ natif

`wasm/policy_parity.mjs --all` rejoue `data/policy_reference.bin` (1 443 décisions : 1 321
`instant`, 92 `normal`, 30 `thorough`, dont 7 refus ; chaque catégorie de la spec §8 couverte) à travers `Evaluator.policy` :
**0 écart d'action, max|Δ| = 0 sur les équités, 0 non bit à bit** — module SIMD, tous niveaux ;
module scalaire, niveau `instant`. La politique hérite du bit à bit de T91.

## 4. Le coût de la lecture exacte

Elle tourne à chaque décision avant le jet. Sur 19 216 positions tirées de 200 parties aléatoires
(natif, `-O2`) : **23 µs en moyenne, 6,9 ms au pire**, 154 défaites certaines lues. Deux bornes
arithmétiques (pips et dés nécessaires) et l'ordre des essais (gros jets, coups les plus avancés
d'abord) l'ont ramenée d'un pire cas de 1,6 s ; aucune réponse n'a changé (mêmes 154, corpus
rejoué à l'identique).

## 5. Le niveau `normal` en match contre gnubg

Protocole T35 inchangé (`bench/run_t35.py --mode match --ours-policy normal`) : gnubg 2-ply
filtre `(0,1,3)` videau 2-ply, longueur 7, scores échantillonnés, graine `20260810`, build
`NATIVE_FP=1`, 8 ouvriers `nice`. **Les dés de T35** (`--dice-key-from
docs/mesures/t35-match-v2.jsonl`) : la paire i rejoue la situation de la paire i de T35, ce qui
permet l'écart **apparié** (`bench/report_policy.py`). Le niveau `normal` diffère du réglage de
T35 par son seul filtre racine en triplet, et le moteur a bougé depuis T35 (T85, T88, forme close
de `level_solve`) : l'identité du §2 ne suffit donc pas, d'où cette mesure.

**Échantillon au 2026-10-05, 122 paires (indices 0..124)** — une hypothèse de travail, pas un
verdict de force :

| | MWC | IC 95 % |
|---|---|---|
| politique `normal` | 50,82 % | [44,67 ; 56,97] |
| T35, mêmes indices | 52,46 % | [46,72 ; 58,20] |
| T35, 50 000 paires (`2026-08-26-T35-verdict.md`) | 50,42 % | [50,16 ; 50,69] |
| **écart apparié politique − T35** | **−1,64 pt** | **[−6,15 ; +2,87]** |

96 paires sur 122 au même résultat net. L'écart apparié contient zéro : **compatible avec T35**,
à une résolution de ±4,5 points seulement.

**Dimensionnement, mesuré sur cet échantillon** : écart-type de l'écart apparié 0,511 par paire,
soit une demi-largeur d'IC de ±2,2 points de MWC à 500 paires, ±1,1 à 2 000, ±0,5 à 10 000.
Retrouver T35 **dans son propre intervalle** (±0,26) demanderait ~37 000 paires. Débit mesuré :
~0,09-0,11 paire/s à 8 ouvriers sur ce poste chargé, soit ~6 h pour 2 000 paires.

**Campagne complète, 2 000 paires (indices 0..1999)**, 322,8 min à 8 ouvriers :

| | MWC | IC 95 % |
|---|---|---|
| politique `normal` | 50,02 % | [48,62 ; 51,42] |
| T35, mêmes indices | 49,75 % | [48,38 ; 51,10] |
| **écart apparié politique − T35** | **+0,27 pt** | **[−0,83 ; +1,38]** |

1 570 paires sur 2 000 au même résultat net. L'écart apparié contient zéro et sa demi-largeur
(±1,1 point) est celle que prévoyait le dimensionnement : **le niveau `normal` est compatible
avec T35 à ±1,1 point de MWC**. L'écart de −1,64 point de l'échantillon était du bruit. Ce
n'est pas une identité dans l'intervalle propre de T35 (±0,26), qui demanderait ~37 000 paires.

Journal : `docs/mesures/politique-t35-match.jsonl` ; le chiffre se relit par
`bench/report_policy.py --journal docs/mesures/politique-t35-match.jsonl --reference
docs/mesures/t35-match-v2.jsonl`.

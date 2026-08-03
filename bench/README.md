# bench/

Les bancs de mesure. | Banc | Objet |
|---|---|
| `bench_oracle.py` | Débit de l'oracle GNU Backgammon (T03) |
| `run_round_robin.py` | Matrice de force entre moteurs, avec IC 95 % bootstrap (T04) |
| `bench_throughput.py` | Les débits réels : règles, codec, oracle, self-play, mémoire (T05) |

À venir : T21 (banc de débit navigateur, piste bureau).

## Le piège que tout banc doit éviter ici

`gnubg_nn` **met les évaluations en cache**. Chronométrer une boucle sur une position répétée
gonfle le chiffre d'un facteur **1 315** au 1-ply. Et des positions consécutives d'une même
partie partagent leurs sous-arbres : elles se répondent l'une l'autre par le cache. Tout banc
doit donc mesurer sur des positions **distinctes et non apparentées** — une par partie — avec
une **tranche disjointe par profondeur**. Détail dans `docs/mesures/2026-08-03-T03-oracle.md`.

## La règle qui gouverne ce répertoire

> **Une conclusion de performance se mesure, elle ne se déduit pas.**

Aucun chiffre de débit, de latence ou de taille ne se tire d'une lecture de code ni d'une
extrapolation. Tout rapport produit ici dit explicitement ce qui est **mesuré** et ce qui
reste **hypothèse** — la pénalité WebAssembly (estimée ×1,5 à ×2,5) est aujourd'hui une
hypothèse, et toute la frontière 2-ply / 3-ply en dépend.

Les rapports sont consignés dans `docs/mesures/`, avec leur date et leur configuration
exacte (`make env`).

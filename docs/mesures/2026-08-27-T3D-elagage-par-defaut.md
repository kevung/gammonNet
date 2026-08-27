# T3D — l'élagage devient le défaut, et ce que ça coûte, mesuré deux fois

**Date** : 2026-08-27 · **Machine** : la machine de calcul · **Branche** : `t3d-elagage-par-defaut`

> **La décision.** Le réseau d'élagage était branché mais éteint depuis T3A, faute d'une mesure de
> force. Il devient le défaut à `k = 12`, et cette fiche porte les deux mesures qui l'autorisent.
>
> **Pourquoi deux.** Aucune ne suffit seule. La mesure **par décision** est appariée sur la même
> position, donc précise, mais elle rend de l'équité par décision — pas la métrique du `BRIEF`. La
> mesure **en ppg** est la bonne métrique, mais son intervalle est plus large que l'effet cherché.
> Ensemble elles bornent le coût ; séparément, l'une est hors métrique et l'autre non concluante.

## La mesure en ppg

Élagué `k=12` contre non élagué, **le même moteur des deux côtés à ceci près**, dés communs, money
cubeful, 2-ply filtre `(0,1,3)`, videau 2-ply.

| | |
|---|---|
| volume | **10 000 paires** (20 000 parties), graine 20260810 |
| résultat | **−0,0049 ppg** [−0,0336 ; +0,0231] |
| durée | 538 min, 24 ouvriers |
| empreinte d'évaluation | `3f5f3c8a1ffad278`, identique des deux côtés |

**L'intervalle contient zéro**, et le point est du signe attendu — l'élagage ne peut pas améliorer,
il ne peut que ne rien coûter. Ce que cette campagne établit est donc une **borne** : le coût est
inférieur à ~0,028 ppg.

**Elle ne pouvait pas faire mieux, et c'était su d'avance.** L'effet attendu vaut de l'ordre de
0,013 ppg (+0,00023 d'équité par décision × ~55 décisions — un ordre de grandeur, pas une mesure),
soit la moitié de l'intervalle. L'appariement aide moins qu'espéré : **79 % des paires rendent
exactement zéro**, mais les 21 % restantes divergent assez pour laisser l'écart-type à 2,52. Aller
à ±0,008 aurait demandé 100 000 paires et quatre jours ; le dimensionnement a été arrêté à
10 000 en connaissance de cause.

## La mesure par décision, qui porte la conclusion

`bench/prune_search.py`, 300 décisions de contact et 150 de course, arbitre = la recherche non
élaguée elle-même :

| `k` | ×temps | accord | perte/décision | IC 95 % |
|---|---|---|---|---|
| 3 | ×9,05 | 80,0 % | +0,00389 | [+0,00232 ; +0,00585] |
| 5 | ×6,16 | 90,7 % | +0,00182 | [+0,00061 ; +0,00353] |
| 8 | ×4,75 | 96,3 % | +0,00031 | [+0,00002 ; +0,00083] |
| **12** | **×3,90** | **98,3 %** | **+0,00023** | **[−0,00000 ; +0,00067]** |

**Pourquoi `k = 12` et pas plus serré.** À `k=3` la perte vaut +0,00389 par décision — **dix-huit
fois ce qu'un ply entier de profondeur rapporte** (T36 : +0,00022). Ce n'est pas un réglage
« rapide », c'est un réglage qui joue moins bien. À `k=12` la perte est dans le bruit en contact et
le gain reste ×3,9 : c'est le seul point de la courbe où l'on ne paie rien de mesurable.

**La course reste le point faible** : 91,3 % d'accord à `k=12` contre 98,3 % en contact, cohérent
avec le rappel top-5 mesuré en T3A (83,6 % contre 94,2 %). Un `k` par terrain n'a pas été mesuré ;
c'est nommé, pas traité.

## Ce que le défaut change concrètement

- `GammonNetCubePlayer` porte `prune_k = 12` et `prune_model`. `prune_k = 0` rend la recherche
  d'avant, **bit pour bit**.
- **Le nom du joueur le dit** : `gammonnet-2ply-f0/1/3-cube2-p12`. Une configuration ne peut pas se
  déguiser en une autre dans un journal, et deux campagnes de réglages différents ne peuvent pas
  se mélanger sans que l'en-tête le montre.
- **Un réseau d'élagage absent est refusé, pas ignoré.** Un élagage silencieusement inactif ferait
  tourner une configuration qui n'est pas celle que le nom annonce — la classe d'erreur que ce
  dépôt refuse par principe.
- `bench/run_t35.py` accepte `--ours-prune-k` et `--theirs-prune-k`.

## Ce que cela n'autorise pas

- **Les journaux T35 existants ne sont pas comparables** à une campagne future menée au défaut :
  ce n'est plus le même joueur. Le nom et l'en-tête le disent, mais il faut le savoir avant de
  comparer deux chiffres.
- **Le verdict de T35 n'est pas rejoué.** « Équivalent à gnubg » a été mesuré sans élagage ; la
  borne ci-dessus dit que l'élagage ne le déplace pas de plus de ~0,028 ppg, elle ne le remesure
  pas.

## Reproduire

```bash
python bench/run_t35.py --mode money --pairs 10000 --workers 24 \
    --journal docs/mesures/t3d-elagage-force.jsonl \
    --ours-ply 2 --ours-filter 0,1,3 --theirs self \
    --ours-prune-k 12 --theirs-prune-k 0
python bench/report_t35.py --journal docs/mesures/t3d-elagage-force.jsonl
```

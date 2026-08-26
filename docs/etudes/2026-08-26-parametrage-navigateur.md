# Ce qu'on expose à l'utilisateur dans le navigateur

**Date** : 2026-08-26 · **Statut** : proposition, adossée aux coûts natifs mesurés

> **Le principe.** On n'expose pas des `ply` et des `filter`. On expose des **préréglages nommés
> avec leur budget de temps**, comme gnubg le fait (Quick / Normal / World Class / Supremo) — parce
> que le seul chiffre qui intéresse quelqu'un qui analyse un match est *« combien de temps ça va
> prendre »*, et que ce chiffre dépend de son appareil.
>
> **La réserve, qui vaut pour toute cette page.** Les coûts ci-dessous sont **natifs**. Le
> transport vers le navigateur n'est pas un facteur constant : le traitement par lot y rend
> ×2,21 (T21) et non ×8,5, or c'est précisément le lot qui porte les gains récents. **Rien ici
> n'est un chiffre navigateur tant qu'il n'a pas été chronométré dans un navigateur.**

## Les coûts natifs, mesurés

Mono-fil, machine calme, après le regroupement des lots :

| configuration | s/décision | un match de 7 points *(~130 décisions)* |
|---|---|---|
| 0-ply | 0,0013 | ~0,2 s |
| 2-ply `(0,1,3)`, `k=3` | 0,24 | ~31 s |
| 2-ply `(0,1,3)`, `k=5` | 0,35 | ~46 s |
| 2-ply `(0,1,3)` sans élagage | 2,01 | ~4,4 min |
| 3-ply `(0,1,1,5)`, `k=5` | 12,2 | ~26 min |
| 3-ply `(0,1,1,5)` sans élagage | 70,6 | ~2,5 h |
| **4-ply `(0,1,1,1,3)`, `k=3`** | **100,1** | **~3,6 h** |
| **4-ply `(0,1,1,1,5)`, `k=5`** | **256,9** | **~9,3 h** |
| rollout 1 296 essais, tronqué à 11, 0-ply | 30,5 par position | — |

## Ce que le 4-ply change à la proposition : il la simplifie

Le 4-ply existe depuis aujourd'hui (`GN_MAX_PLY = 4`) et **l'équivalence des numéros de ply avec
gnubg est mesurée**, pas supposée (`docs/mesures/2026-08-26-T3B-ply-equivalence` : identité de la
récursion vérifiée à 2,4e-07 chez gnubg, exactement 0 chez nous).

Mais **il n'a rien à faire dans une interface interactive**. Trois heures et demie pour un match
sur *desktop natif*, avant même la pénalité navigateur, et pour un gain de force que T36 a mesuré
à +0,00022 d'équité par ply — dans le bruit. **Le 4-ply est un instrument de vérification, pas un
réglage utilisateur.** Il sert à établir qu'on reste à hauteur de gnubg à sa profondeur maximale ;
il ne sert pas à analyser des parties.

Même chose, en moins net, pour le 3-ply : 26 minutes par match à `k=5`.

## Les préréglages proposés

| nom | interne | budget natif / décision | à quoi il sert |
|---|---|---|---|
| **Instantané** | 0-ply | 1,3 ms | survol d'un match entier, repérage des coups à revoir |
| **Normal** | 2-ply `(0,1,3)`, élagage `k=3` | 0,24 s | le réglage par défaut : un match en une minute |
| **Approfondi** | 2-ply `(0,1,3)`, élagage `k=8` | ~0,46 s | une décision qu'on veut trancher |
| **Rollout** | 0-ply, 1 296 essais, tronqué 11 | ~30 s / position | l'arbitre, sur une décision précise |

**Ce qui n'est pas un préréglage mais un réglage à part**, parce qu'il change la *question* et non
la précision :

- **Le score du match et l'état du videau.** Une même position ne se joue pas pareil à 2-away
  qu'en money, et c'est invisible si on ne le demande pas.
- **Money / match**, avec Jacoby en money.

**Ce qu'on n'expose pas** : `filter`, `prune_k`, `truncate`, la profondeur en clair. Ce sont des
réglages d'instrument, et les exposer déplacerait sur l'utilisateur un arbitrage qualité/temps
que les préréglages ont déjà tranché avec des chiffres.

## Ce qu'il faut avoir mesuré avant de figer ces préréglages

1. **Le coût réel dans le navigateur**, avec la méthode de T21 — desktop et mobile, sur la page
   statique publiée. Les budgets ci-dessus ne se transportent pas.
2. **Ce que `k=3` coûte en qualité**, en match. Mesuré par décision : 80,0 % d'accord avec la
   recherche non élaguée, +0,00389 d'équité perdue par décision. Ce n'est **pas** rien —
   c'est dix-huit fois ce qu'un ply de profondeur rapporte. Si « Normal » doit être `k=3`, il faut
   d'abord chiffrer ce que cela coûte **en ppg ou en MWC**, pas seulement par décision.
3. **Le nombre de fils réellement disponibles** (Web Workers), qui décide si un match s'analyse en
   parallèle ou décision par décision.

**Tant que 2 n'est pas mesuré, le préréglage « Normal » devrait être `k=8`** — 96,3 % d'accord,
+0,00031 de perte, et ~0,46 s par décision. Le conservatisme coûte ici une minute par match.

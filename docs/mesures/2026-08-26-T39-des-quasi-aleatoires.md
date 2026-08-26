# T39 — les dés quasi-aléatoires ne rapportent rien ici, mesuré

**Date** : 2026-08-26 · **Machine** : la machine de calcul · **Branche** : `t39-des-quasi-aleatoires`

> **La question.** `show rollout` montre que gnubg active les **dés quasi-aléatoires** par défaut,
> et nous ne le faisons pas. Un rollout qui *tire* son premier jet voit les trente-six ouvertures à
> peu près — pas exactement — `essais/36` fois chacune ; cet écart est du bruit d'échantillonnage
> posé sur la quantité mesurée, et il est en principe évitable. Combien vaut-il ?
>
> **La réponse : rien de mesurable.** Variance **÷1,00** à 1 296 essais, **÷1,03** à 144. Le
> mécanisme est implémenté fidèlement, testé, et **éteint par défaut** — la fiche existe pour que
> personne ne recommence.

## Ce qui a été construit

Le premier jet — et, en option, le second — sont **assignés** au lieu d'être tirés : chaque bloc de
trente-six essais couvre les trente-six paires ordonnées **exactement une fois**. `quasi_random` dit
combien de plis sont stratifiés ; 0 rend les résultats précédents bit pour bit.

Deux propriétés étaient obligatoires, et `tests/test_quasi_random.py` les tient :

- **Les dés restent une fonction pure de `(graine, essai, ply)`.** La permutation est dérivée de la
  graine et de l'indice de bloc, jamais reportée d'un appel à l'autre. C'est ce qui rend les dés
  communs réellement communs entre processus, ordres et profondeurs — la propriété que la note
  d'en-tête de `gn_rollout.c` existe pour protéger. Une stratification à état l'aurait cassée en
  silence.
- **Stratifier deux plis ne les verrouille pas ensemble.** L'indice est décalé de `ply × bloc`, donc
  quelle ouverture rencontre quelle réponse tourne d'un bloc à l'autre. Sans ce décalage on aurait
  remplacé du bruit par un **biais** — pire, parce qu'invisible et systématique.

Le test tient aussi un **témoin** : le hash brut ne couvre pas les trente-six paires par bloc. Sans
lui, le test principal pourrait passer sur un générateur uniforme par accident.

## La mesure

La stratification ne change pas la dispersion des essais **entre eux** ; elle supprime l'erreur
d'échantillonnage sur la distribution des **ouvertures**. Elle est donc invisible dans un run et
visible **entre** les runs : on relance le même rollout, sur la même position, en ne changeant que
la graine, et on regarde la dispersion des estimations.

8 positions de contact, 48 graines, politique 0-ply, tronqué à 11 plis :

| essais par rollout | variance divisée par | temps | biais |
|---|---|---|---|
| 1 296 | **1,00** | ×0,991 | +0,000486 |
| 144 | **1,03** | ×1,006 | −0,000748 |

**L'hypothèse du faible volume est réfutée aussi.** Elle était raisonnable — à 144 essais l'erreur
d'échantillonnage sur les ouvertures est neuf fois plus grande qu'à 1 296 — et elle ne tient pas.

**Pourquoi, vraisemblablement** *(hypothèse, non mesurée)* : la variance d'un rollout est dominée
par le déroulement des parties, pas par la composition du premier jet. Supprimer exactement
l'erreur sur les ouvertures retire une part de variance qui était déjà négligeable devant le reste.

## Ce que la fiche ne dit pas

- **Que gnubg a tort de le faire.** Ses rollouts ne sont pas les nôtres — politique, troncature,
  réduction de variance et nombre d'essais diffèrent. La mesure porte sur **notre** rollout.
- **Que ça ne servira jamais.** Le mécanisme reste disponible, éteint. S'il devient utile — un
  rollout très court dans le navigateur, par exemple — il est là, et le chiffre à battre est ici.

## Le code a été abandonné — ce qu'il faudrait réécrire, si jamais

**La branche `t39-des-quasi-aleatoires` n'est pas mergée et a été supprimée.** Garder un mécanisme
mesuré inutile, c'est de la complexité que quelqu'un devra comprendre un jour sans raison. Ce qui
survit est cette fiche, et elle est écrite pour être suffisante.

Ce qu'il y avait, et qu'il faudrait refaire à l'identique :

- **Un champ `quasi_random` dans `GnRolloutConfig`** : combien de plis sont stratifiés. 0 = éteint,
  résultats précédents bit pour bit.
- **`roll_at(graine, essai, ply, qr_plies, ...)`** : si `ply < qr_plies`, l'indice dans le bloc est
  `(essai % 36 + ply × (essai / 36)) % 36`, puis on applique une permutation de 0..35 tirée par
  Fisher-Yates depuis un SplitMix64 semé de `(graine, ply, bloc)`. Le code 0..35 devient
  `(code/6 + 1, code%6 + 1)`.
- **Le décalage `ply × bloc` est la partie qu'on oublierait** : sans lui, la même ouverture
  rencontrerait toujours la même réponse, et on aurait remplacé du bruit par un biais.
- **Quatre tests** : couverture exacte par bloc ; un **témoin** montrant que le hash brut ne l'a pas ;
  la pureté de la fonction (mêmes dés dans n'importe quel ordre d'appel) ; et la non-corrélation
  des deux plis stratifiés.
- **Le banc** relançait le même rollout sur la même position en ne changeant que la graine, et
  comparait la dispersion des estimations — la seule façon de voir un effet qui est invisible
  *dans* un run et visible *entre* les runs.

**Le chiffre à battre, si quelqu'un recommence : ÷1,00.**

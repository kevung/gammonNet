# T78 — Distiller la table exacte : la queue de fin de partie, battue

**Date** : 2026-08-28 · **Machine** : `melbaa`, 14 cœurs / 28 fils, libre · **Branche** :
`t78-bearoff-distillation`

> T38 avait posé le chiffre, et laissé la piste ouverte. Branchée, la table bilatérale ferme le
> trou de fin de partie en entier — mais elle pèse 1,2 Gio et reste native. Ce qui part dans un
> navigateur, c'est le réseau, et il paie la queue : **0,0919 d'équité sur la pire décision**,
> quand GNU Backgammon, qui consulte sa table, ne dépasse jamais 0,0023.
>
> *« C'est la queue qui coûte, pas la moyenne. »*

## Le résultat

**8 000 décisions de bearoff**, notées **exactement** par la table bilatérale. Le tirage, la
notation et la définition de la perte sont **importés de `bench/exact_gap.py`** : à graine égale,
ce sont les décisions de T38, pas des décisions équivalentes.

| réseau | octets (f32) | (f16) | accord | perte moy. | si désaccord | p99,9 | **pire** | > 0,0023 |
|---|---|---|---|---|---|---|---|---|
| 128→64, comptes seuls | 82 996 | 41 474 | 95,5 % | 0,0000831 | 0,00186 | 0,0096 | 0,0257 | 87 |
| 256→128, comptes seuls | 231 476 | 115 714 | 97,3 % | 0,0000273 | 0,00101 | 0,0040 | 0,0125 | 32 |
| 256→128, **tanh** | 231 476 | 115 714 | 98,1 % | 0,0000268 | 0,00139 | 0,0045 | 0,0141 | 30 |
| 512→256, comptes seuls | 725 044 | 362 498 | 97,8 % | 0,0000133 | 0,00059 | 0,0028 | 0,0046 | 12 |
| **code 4** →128→64 | 285 108 | 142 530 | 98,6 % | 0,0000048 | 0,00034 | 0,0009 | 0,0046 | 2 |
| **code 8** →128→64 | 487 220 | 243 586 | 99,1 % | 0,0000026 | 0,00028 | 0,0007 | 0,0024 | 1 |
| **code 16** →256→128 | 1 056 308 | 528 130 | **99,2 %** | **0,0000017** | **0,00022** | **0,0006** | **0,0014** | **0** |
| | | | | | | | | |
| *notre grand réseau, 0-ply* | *2,1 Mio* | | *94,5 %* | *0,0002773* | *0,00501* | *0,0310* | *0,0474* | *213* |
| *notre grand réseau, 1-ply* | *2,1 Mio* | | *95,3 %* | *0,0002028* | *0,00434* | *0,0249* | ***0,0919*** | *157* |
| *GNU Backgammon, 0-ply* | *(sa table)* | | *99,8 %* | *0,0000010* | *0,00043* | *0,0003* | *0,0023* | *0* |
| *GNU Backgammon, 1-ply* | *(sa table)* | | *99,8 %* | *0,0000009* | *0,00041* | *0,0002* | *0,0023* | *0* |

**La queue est battue, et le seuil que la fiche s'était fixé avant la mesure — perte moyenne
≤ 0,00005 **et** pire cas ≤ 0,0023 — est franchi par un candidat, `code 16`.** Son pire cas,
**0,00140**, passe sous celui de GNU Backgammon (0,00229) ; aucune de ses 8 000 décisions ne
dépasse le pire cas de gnubg, là où notre grand réseau en compte 157.

Le prix : **528 Kio** de poids en float16, contre **1,2 Gio** de table. Un rapport de **2 400**.

`code 8` en approche à un cheveu — 0,00235 contre le seuil de 0,0023, **une** décision sur 8 000
au-delà — pour la moitié des octets. Il ne passe pas la fiche : il passe à 0,00005 près, et c'est
écrit ainsi plutôt qu'arrondi.

## Ce que ce tableau vaut : la ligne de référence reproduit T38 au chiffre près

Le même passage a mesuré nos moteurs actuels et gnubg sur les mêmes décisions. Comparé à
[T38](2026-08-06-T38-table-exacte.md) :

| moteur | T38 (2026-08-06) | ici (2026-08-28) |
|---|---|---|
| grand réseau 0-ply | 94,5 % · 0,00028 · 0,00501 · 0,0474 | **94,5 % · 0,00028 · 0,00501 · 0,0474** |
| grand réseau 1-ply | 95,3 % · 0,00020 · 0,00434 · 0,0919 | **95,3 % · 0,00020 · 0,00434 · 0,0919** |
| GNU Backgammon 0-ply | 99,8 % · 0,00000 · 0,00043 · 0,0023 | **99,8 % · 0,00000 · 0,00043 · 0,0023** |

Quatre colonnes, trois moteurs, deux machines, deux builds de gnubg : identiques. Ce n'est pas une
coïncidence heureuse, c'est la conséquence d'avoir **importé** le tirage plutôt que de le
réécrire — et c'est ce qui autorise à lire les lignes du distillé dans le même tableau que celles
de T38.

## Les deux familles, et laquelle dépense mieux ses octets

**Comptes seuls** : le réseau reçoit six nombres par camp — les pions sur chaque point — et doit
redécouvrir à chaque évaluation ce qu'est une course.

**Code appris** : il n'y a que **12 376 dispositions** par camp. Leur donner `d` nombres chacune
est une pièce d'artefact légitime, et mathématiquement c'est le même réseau nourri de l'identité
de la disposition.

La courbe tranche, et pas du côté attendu :

- **`code 4`, à 285 Kio, bat `512→256` à 725 Kio** — deux fois moins d'octets, deux fois moins
  d'erreur moyenne, et le même pire cas. Ce n'est pas « plus gros donc mieux » : c'est une
  meilleure façon de dépenser les octets.
- À travers toute la famille à comptes seuls, quadrupler la taille (82 Kio → 725 Kio) divise la
  perte moyenne par 6. Dans la famille à code appris, **doubler** la taille la divise par 3.

**La tanh, elle, coûte exactement là où on ne la surveillait pas** : à taille et à recette
égales, `256→128` en tanh a la même perte moyenne que sa jumelle linéaire (0,0000268 contre
0,0000273) et **un pire cas exhaustif deux fois plus grand** (0,162 contre 0,095). L'unité saturée
n'a pas de gradient à donner précisément là où le classement est le plus difficile. Le soupçon
était le bon, l'ordre de grandeur que j'en attendais ne l'était pas — c'est la queue qui bouge,
pas la moyenne.

## Le float16 ne coûte rien

Les poids arrondis au demi-précision rendent, sur les mêmes 8 000 décisions, **exactement les
mêmes lignes** — accord, perte moyenne, perte au désaccord, p99,9, pire cas, tous identiques pour
les trois candidats à code appris. Sur le balayage exhaustif, l'erreur maximale de
`code 16` passe de **0,0154867 à 0,0155010** — l'arrondi coûte 1,4e-5 sur le pire cas de tout le
domaine, cinquante fois moins que la résolution de la table elle-même (3,05e-5, soit un pas de
son échelle 16 bits). L'artefact est donc de moitié : `code 16` en 528 Kio, `code 8` en 244 Kio.

## La borne exhaustive : ce qu'elle donne, et pourquoi elle ne suffit pas

Le domaine est **fini et entièrement connu** — 153 165 376 paires — et le réseau est assez petit
pour qu'on les lui pose toutes, en une minute. « Erreur maximale » n'est donc pas ici une
estimation : c'est l'erreur maximale.

Et elle **borne** la queue. Si l'évaluateur préfère un coup `c` au meilleur coup `b`, alors
`u(c) ≥ u(b)`, donc

    v(b) − v(c) = (v(b) − u(b)) + (u(b) − u(c)) + (u(c) − v(c)) ≤ 2e

La perte par décision ne peut donc pas dépasser **deux fois l'erreur maximale**, sur toutes les
décisions du domaine — y compris celles que personne n'a tirées. Aucun banc échantillonné ne dit
cela ; il dit ce qu'il a vu.

**Mais la borne n'est pas atteinte, et elle ne pouvait pas l'être.** Pour `code 16` elle vaut
0,031 — vingt fois la perte réellement mesurée. La raison se lit dans le domaine lui-même : les
pires paires sont des positions du **dernier jet**, où l'équité est un rationnel déterminé par une
poignée de jets. La pire de toutes, (9, 7), oppose un pion sur la 1 et un sur la 3 à deux pions
sur la 1 : l'équité exacte y vaut 0,8889, soit 34 jets sur 36, sur un plateau parfaitement plat.
Et la colonne « l'adversaire sort au prochain jet » ne compte que **15 dispositions sur 12 375**
d'équité positive — les cas où l'on sort tout d'un coup, qui sont des positions **terminales**,
calculées et jamais soumises au réseau.

La borne inclut donc des paires auxquelles aucune décision n'est sensible. Le banc rend aussi la
**borne par ligne** — les candidats d'une décision partagent la disposition de l'adversaire, donc
seule leur ligne les concerne : médiane 0,0060, p90 0,0089 pour `code 16`. Toujours au-dessus de
0,0023 : la garantie *a priori* n'est pas acquise, et la fiche est franchie par la **mesure**, pas
par la borne. C'est dit ici plutôt que laissé à deviner.

## Les trois étages, et ce que chacun a fait

Sur `code 16`, à chaque étage, l'erreur sur la totalité du domaine :

| étage | moyenne | rms | pire | paires > 0,01 |
|---|---|---|---|---|
| 1 — régression uniforme, 80 000 pas | 4,55e-4 | 6,02e-4 | 0,0259 | 363 |
| 2 — fouille exhaustive, 10 tours | 5,47e-4 | 7,36e-4 | **0,0082** | — |
| 3 — affinage par décision, 20 000 pas | **4,29e-4** | **5,66e-4** | 0,0155 | **64** |

Le tableau se lit en trois temps, et le troisième est le plus instructif :

- **la fouille divise le maximum par trois** (0,0259 → 0,0082) en payant la moyenne — c'est
  exactement l'arbitrage qu'on lui demande, et il est visible plutôt que supposé ;
- **l'affinage par décision reprend une partie de ce maximum** (0,0082 → 0,0155) tout en
  améliorant la moyenne et le compte des paires grossièrement fausses (363 → 64) ;
- ce qui **n'est pas** une contradiction : l'objectif n'est pas le maximum sur le domaine, c'est
  la perte par décision, et un étage qui échange du maximum inutile contre du classement utile
  fait précisément son travail.

### L'ablation : ce que chaque étage rapporte sur la métrique qui décide

Le tableau ci-dessus dit ce que les étages font à l'erreur ; il ne dit pas ce qu'ils font à la
**perte par décision**, qui est la seule chose que la fiche juge. Le gagnant a donc été
réentraîné tronqué — même graine, mêmes réglages, seuls les étages changent — et remesuré sur les
mêmes 8 000 décisions :

| recette | accord | perte moy. | si désaccord | p99,9 | pire | > 0,0023 |
|---|---|---|---|---|---|---|
| régression seule | 96,0 % | 0,0000200 | 0,00051 | 0,0031 | 0,0062 | 18 |
| \+ fouille exhaustive | 96,1 % | 0,0000122 | 0,00038 | 0,0016 | 0,0031 | 4 |
| \+ affinage par décision *(le réseau publié)* | **99,2 %** | **0,0000017** | **0,00022** | **0,0006** | **0,0014** | **0** |

**Les trois étages gagnent leur place, et le dernier est le plus rentable.** La fouille divise le
pire cas par deux (0,0062 → 0,0031) sans presque toucher au taux d'accord — elle corrige des
erreurs rares et grosses, ce pour quoi elle est faite. L'affinage par décision, lui, fait les deux
à la fois : l'accord saute de 96,1 % à 99,2 % et le pire cas est encore divisé par deux. C'est
attendu et c'est mesuré : il est le seul étage dont la perte *est* la quantité qu'on publie.

**Une réserve de lignée, et sa taille.** Les deux premières lignes sont la même lignée ; la
troisième est le réseau publié, entraîné avec **six** fils là où l'ablation en a eu sept. Or
l'entraînement torch sur CPU n'est reproductible au bit près qu'à **nombre de fils constant** :
les deux ablations, lancées ensemble à sept fils, rendent après régression exactement les mêmes
chiffres (moyenne 4,643e-4, pire 0,0233 en (140, 2)), tandis que le réseau publié rendait
4,546e-4 et 0,0259. L'écart entre lignées est donc de 2 % sur la moyenne et 10 % sur le maximum —
dix fois plus petit que les effets qu'on lit dans le tableau, mais il est réel et il est écrit.
La provenance de chaque réseau enregistre son nombre de fils pour cette raison.

## Le coût d'évaluation — un compte, pas une vitesse

`code 16` fait **65 664 multiplications-accumulations** par position, `code 8` en fait **22 592**,
contre **526 976** pour le grand réseau (196→512→512→256→128→5). Dans le domaine de la table,
remplacer l'un par l'autre divise donc le compte d'opérations par 8 à 23.

**Ce n'est pas une mesure de vitesse et ne doit pas être lu comme telle** (règle 3 de
`CLAUDE.md`) : la consultation du code appris est un accès mémoire que ce compte ignore, et rien
n'a été chronométré. Le gain réel, natif et WebAssembly, se mesurera au banc, dans la fiche du
branchement.

## Reproduire

```bash
# 306 Mio de colonne cubeless, relus par le lecteur de T38
python tools/build_bearoff_matrix.py

# 2 000 000 de décisions, chaque coup légal noté exactement
python tools/build_bearoff_decisions.py --decisions 2000000 --workers 26

# les trois étages
python tools/train_bearoff_net.py --hidden 256,128 --output linear --embedding 16 \
  --steps 80000 --batch 8192 --lr 3e-3 --threads 7 \
  --mine-rounds 10 --mine-steps 4000 --mine-keep 1000000 --mine-lr 5e-4 \
  --decision-corpus build/bearoff_decisions.npz --decision-steps 20000 --decision-lr 2e-4 \
  --out models/bearoff_code16_256_128.bin

# les 153 165 376 paires, float32 et float16
python bench/bearoff_exhaustive.py --net models/bearoff_code16_256_128.bin --fp16

# les 8 000 décisions de T38, avec la ligne de référence
python bench/bearoff_distill.py --net models/bearoff_code16_256_128.bin \
  --decisions 8000 --workers 26 --baseline --plies 0,1 --with-gnubg
```

Sorties : [`t78-*-decisions.json`](.) et [`t78-*-exhaustif.json`](.), une par candidat, plus
[`t78-reference-decisions.json`](t78-reference-decisions.json). Provenance et empreintes des
poids dans `models/bearoff_*.provenance.json`.

## Un incident de format, et pourquoi il se voit

Le format de poids a reçu un champ — la largeur du code appris — **pendant** la campagne. Les
quatre premiers candidats, écrits avant, ne se relisaient plus, et ma migration d'en-tête s'est
trompée de test de version : elle a inséré quatre octets dans deux fichiers qui n'en avaient pas
besoin. Les deux ont été rétablis, et **les sept empreintes sha256 correspondent maintenant à ce
que la provenance enregistrait à l'entraînement** ; les balayages exhaustifs ont été rejoués et
rendent, au dernier chiffre, ce qu'ils rendaient avant la manipulation.

Ce qui a rendu tout cela vérifiable est une ligne du lecteur : il **refuse** un fichier dont les
octets ne se consomment pas exactement. Un lecteur tolérant aurait relu ces poids de travers et
rendu des équités parfaitement plausibles.

## Ce que cette fiche ne fait pas

- **Le branchement.** Rien de tout ceci n'est câblé dans `gn_search` ni compilé en WebAssembly.
  Le verdict d'abord ; le branchement est une fiche à part, avec son propre coût mesuré.
- **Le videau.** La table a quatre colonnes ; nous n'avons distillé que la première, l'équité
  cubeless. Les trois colonnes cubeful restent une piste ouverte, et c'est en fin de course que
  la décision de videau admet une réponse sans variance.
- **Hors domaine.** Au-delà de onze pions par camp ou d'un pion hors du jan intérieur, le réseau
  distillé **refuse** — `contains` est un prédicat testé contre le lecteur de T38, pas une
  hypothèse. C'est le grand réseau qui répond là.
- **Un conteneur float16.** L'arrondi est mesuré sans effet, mais le fichier reste écrit en
  float32 : le format n'a pas encore de variante demi-précision.

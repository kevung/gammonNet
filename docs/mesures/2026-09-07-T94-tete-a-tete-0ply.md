# T94 — le tête-à-tête à dés dupliqués, 0-ply : un million de parties

*2026-09-07 · melbaa (Xeon E5-2683 v3, 14 cœurs / 28 fils), 24 processus ·
`bgsage` 1.7.20260829, modèle `stage9` par défaut · graine 20260907*

> **Ce chiffre ne dépend d'aucun arbitre.** C'est sa raison d'être : T93 mesure une perte
> d'équité contre un arbitre qui a ses propres goûts, et cette fiche-ci ne mesure que ce qui
> s'est passé sur le damier. Les deux se lisent ensemble ; aucune ne remplace l'autre.

---

## Le résultat

Money **cubeless**, dés communs, paires dupliquées sièges échangés, bootstrap sur les paires.
Les deux moteurs à leur évaluation statique — **profondeur réelle 0 des deux côtés**, ce qui
est leur `1ply` et notre `instant` (T92).

| | ppg | IC 95 % | victoires | parties |
|---|---|---|---|---|
| **gammonNet 0-ply contre le leur** | **+0,0322** | **[+0,0288 ; +0,0356]** | 51,37 % | 500 000 |

**Résidu d'antisymétrie : exactement 0.** Le harnais rend le même chiffre au signe près dans
les deux sens, ce qui est la propriété que T04 exige de lui avant qu'on lise une seule ligne.
Zéro partie abandonnée à la limite de coups. 1 000 000 de parties en 6 541 s.

Relevé brut : [`t94-0ply-tete-a-tete.json`](t94-0ply-tete-a-tete.json).

### Ce que ça veut dire

**À profondeur nulle des deux côtés, notre réseau est le plus fort, et l'écart sort largement du
bruit.** L'intervalle est entièrement positif et large de ±0,0034 ppg — c'est le volume qui
l'achète : `BRIEF.md` §9 fixe la barre du million de parties par paire, et elle est tenue.

Le repère qui donne l'échelle : le même réseau bat **GNU Backgammon 0-ply de +0,0400 ppg**
[+0,0377 ; +0,0425] (T11). Les trois moteurs se rangent donc ainsi à profondeur nulle, sur nos
propres mesures :

    gammonNet  >  eux  >  GNU Backgammon
               ↑         ↑
          +0,0322    ≈ +0,008 (par différence, non mesuré directement)

Le second écart est une **soustraction de deux mesures, pas une mesure** : il suppose une
transitivité que ce dépôt n'a pas vérifiée, et `BRIEF.md` §5 rappelle que les non-transitivités
apparaissent réellement entre moteurs de styles différents. Il est donné pour l'ordre de
grandeur, et il faudrait une troisième colonne de round-robin pour l'affirmer.

---

## Les trois réserves, nommées

**1. Le 0-ply n'est pas leur point de fonctionnement.** Leur modèle `stage9` est un ensemble de
**dix-neuf réseaux** avec une stratégie de paire dédiée aux backgames, et leur étude publiée
porte sur des niveaux de **rollout tronqué**, pas sur l'évaluation statique. Cette mesure dit
que notre réseau est meilleur *à profondeur nulle* ; elle ne dit rien de ce que leur recherche
en fait ensuite. C'est précisément la question que T93 pose au 2-ply, et l'avertissement de T36
vaut ici : **un avantage 0-ply qui ne survit pas à la recherche ne compte pas.**

**2. C'est du cubeless.** Le videau n'est pas joué, et l'arène de ce dépôt ne le joue pas au
0-ply. Une erreur de videau vaut plus du double d'une erreur de coup (DS-08) : ce chiffre ne
porte donc pas sur la moitié la plus chère du jeu.

**3. Le réglage a été vérifié plutôt que supposé.** Les deux moteurs classent leurs coups à
l'équité **cubeless**, ce qui n'est pas le défaut du leur — T92 §4 bis raconte comment le défaut
`cubeful` a d'abord rendu **+0,5375 ppg**, un artefact de protocole plausible et faux.

---

## Ce qui reste ouvert

- **Le 2-ply.** Le même tête-à-tête à la profondeur servie coûte ~20 s par partie et par moteur
  confondus : atteindre l'IC de cette fiche y demanderait des semaines. Une campagne de
  24 000 parties tourne, dont l'intervalle attendu est de l'ordre de ±0,016 ppg — assez pour
  écarter un écart grossier, pas pour trancher un écart fin. C'est T93 qui porte cette
  profondeur, avec un instrument apparié cent fois plus sensible.
- **Le match, et le videau.** Le pilote de campagne cubeful de T35 ne sait aujourd'hui aligner
  que GNU Backgammon ; brancher un troisième moteur y demande de porter sa décision de videau,
  ce que cette fiche n'a pas fait.

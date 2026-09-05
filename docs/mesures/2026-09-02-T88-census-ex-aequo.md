# Les ex æquo du classement : combien, et ce qu'ils changent

**Date** : 2026-09-02 · **Machine** : poste de bureau, AMD Ryzen 7 PRO 6850U (Zen 3, 8 cœurs /
16 fils, AVX2), 14,4 Gio, Linux 7.1.9-arch1-2 · **Chaîne** : gcc (glibc 2.44), emcc 6.0.9-git,
Python 3.13 · **Branche** : `fix/deux-defauts` · **Fiches** : T88, et le premier point de T86

> **Ce document énonce des MESURES.** Les deux seules hypothèses sont nommées comme telles.
>
> La machine n'était pas au repos : charge moyenne entre 1,7 et 7,2 pendant la séance. Les
> chronométrages ci-dessous sont donc donnés en **rapports mesurés dos à dos**, jamais en
> valeurs absolues — même convention que
> `docs/mesures/2026-09-02-optimisation-mesures-d-entree.md`.

## Ce qui était en cause

`compare_candidates` (`src/gn_search.c`) ne comparait que l'équité, et `qsort` n'est pas
stable : l'ordre de deux candidats de **même** équité venait de la libc. Le harnais de parité
compare des équités à 1e-6, donc une permutation d'ex æquo lui est invisible.

## 1. Combien d'ex æquo, réellement

`make tie-census`, corpus T12 (2 050 positions), **les 21 lancers de chaque position**, équités
comparées **bit à bit** (`==` sur le `double`, pas une tolérance).

### 0-ply, sans élagage — 41 779 décisions

| | |
|---|---|
| décisions | 41 779 (dont 35 547 à plus d'un coup) |
| décisions portant **au moins un ex æquo** dans le classement rendu | **802 — 1,92 %** |
| décisions dont le **meilleur coup** est ex æquo | **433 — 1,22 %** des décisions à plus d'un coup |
| paires adjacentes d'équités bit-à-bit égales | 20 364 |
| plus grand groupe d'ex æquo observé | **230 candidats** sur 231 (`DwAA4FGYYQsAAA`, trait noir, 1-1) |

**Le chiffre n'est donc pas zéro**, et la fiche ne se ferme pas sur « défaut théorique ». La
source dominante est identifiée : un coup qui **finit la partie** est valué exactement
(`terminal_value`, l'enjeu entier), et une position où tous les coups gagnent produit autant
d'équités identiques que de coups.

### 2-ply, filtre (0,1,3), élagage k=12 — 12 positions, 252 décisions

Le coût interdit d'en faire plus : une décision coûte ~0,4 s, et chacune fait ici **2 484 tris**.

| | |
|---|---|
| tris internes | 625 621 (24 871 238 candidats triés) |
| tris portant un ex æquo | **355 — 0,057 %**, 360 paires |
| coupes prises (élagage `prune_k` **et** filtre de la passe profonde) | 271 565 |
| **coupes tombant DANS un ex æquo** | **2 — 0,0007 %** |
| classements rendus portant un ex æquo | **0** |

Deux lectures, et la seconde est la plus importante :

- **Au sommet, à 2 ply, les ex æquo disparaissent** : la passe profonde sépare ce que le réseau
  seul laissait égal. Le défaut est donc surtout un défaut de 0-ply — c'est-à-dire du niveau
  `instant`, celui qu'un navigateur joue par défaut.
- **Les coupes, elles, restent exposées.** Une coupe qui tombe entre deux équités égales ne
  permute pas un affichage : elle change **quels coups sont cherchés**. Les équités qui en
  sortent divergent alors bien au-delà de 1e-6. 2 cas sur 271 565 — rare, et d'un autre genre
  que les autres.

## 2. La libc dont l'ordre dépendait — mesuré, pas supposé

Sonde : éléments de 72 octets (`sizeof(GnCandidate)`), cinq équités distinctes tirées au sort,
comptage des ex æquo dont l'ordre d'arrivée est inversé après `qsort`.

| n | glibc 2.44 | Emscripten 6.0.9 (musl, smoothsort) |
|---|---|---|
| 8 | 0 | 0 |
| 32 | 0 | **13** |
| 128 | 0 | **64** |
| 512 | 0 | **297** |
| 2 048 | 0 | **1 184** |

**Le `qsort` de la glibc est stable en pratique ; celui d'Emscripten ne l'est pas.** La cible
qui divergeait est donc exactement celle qui tourne dans le navigateur — et c'est aussi
pourquoi aucun test natif ne pouvait attraper le défaut (vérifié : la suite de non-régression
ajoutée par ce correctif **passe aussi sur le code d'avant**, en natif).

## 3. Ce que la permutation changeait, dans le module livré

Les 433 décisions à meilleur coup ex æquo du §1, rejouées dans le module WebAssembly SIMD et
comparées au classement natif :

| | coup annoncé ≠ natif | classement ≠ natif |
|---|---|---|
| **avant** le correctif | **89 / 433** | 244 / 433 |
| **après** | 4 / 433 | 23 / 433 |

**89 décisions sur 433 où le navigateur annonçait un autre coup que le natif**, à équité
identique au bit près. C'est le défaut, chiffré.

**Le résidu de 4 n'est pas un ex æquo mal trié**, et il a été ouvert : aux rangs concernés les
équités du module ne sont **pas** égales (`-1,9999979…` contre `-1,9999980…`). C'est la
divergence numérique déjà connue entre les deux builds — le module est compilé
`-fassociative-math`, le natif non — et elle reste sous la tolérance de parité (1e-6, vérifiée :
max|Δ| = 6,407e-7). Conséquence à retenir : **l'ensemble des ex æquo est propre à un build**.
Un tri stable rend chaque cible déterministe et rend les trois d'accord **là où elles calculent
les mêmes nombres** ; il ne peut pas faire tenir une égalité exacte que l'arithmétique de l'une
n'a pas produite.

**L'invariant ajouté au harnais discrimine, et c'est vérifié** : sur cette même position
(élagage éteint — à k=12 il ne reste que douze survivants, taille à laquelle musl ne permute
plus rien et où l'invariant passerait sans rien prouver), l'empreinte de l'ordre rendu par le
module vaut `00551a01…` avant le correctif et `71e97e36…` après, cette dernière étant celle du
natif. Le cas à neuf coups gardé à côté, lui, ne discrimine pas — il documente la règle et le
dit.

## 4. Ce que la stabilité coûte

`make bench-decision` avec élagage k=12, 20 décisions, les deux binaires lancés **en
alternance** dans la même minute, huit tours :

| rapport après / avant |
|---|
| 0,959 · 0,944 · 1,108 · 0,980 · 0,935 · 1,053 · 1,024 · 1,025 |

**Médiane 1,00**, étendue 0,94–1,11 — c'est-à-dire le plancher de bruit de la machine et rien
d'autre. Le critère de la fiche (« un tri stable ne doit pas coûter plus que ce que le tri
actuel coûte », le tri pesant 0,16 % d'une décision) est tenu : **aucun surcoût mesurable**.

Le tri livré a deux formes, une seule sortie : insertion sous 48 candidats (ce qu'un nœud réel
trie), fusion ascendante au-dessus (la passe d'élagage sur un double en voit des centaines).
Les deux sont stables, donc la permutation de sortie est la même, y compris quand la fusion
retombe sur l'insertion faute de tampon.

## 5. Ce qui n'a pas bougé

- **Natif, 0-ply, corpus T12 entier** : 41 779 classements dumpés avant et après, `diff` = **0
  ligne**. Attendu, puisque la glibc était déjà stable.
- **Natif, 2-ply k=12, 12 positions** : 252 classements, `diff` = **0 ligne**.
- **Parité WebAssembly ↔ natif** : ✅ scalaire max|Δ| = 0,000e+0, ✅ SIMD max|Δ| = 6,407e-7,
  tolérance 1e-6 inchangée.
- **Suite Python** de la recherche et du videau : 1 327 passés, 3 ignorés. Suite complète :
  **1 737 passés, 45 ignorés**, plus 16 erreurs dans `tests/test_serve.py` qui n'ont rien à voir
  ici — le serveur refuse de démarrer faute de l'artefact float16 épinglé, absent de ce
  worktree (`python tools/fetch_release.py`). Non lancé : `tests/test_oracle.py` (GNU
  Backgammon), et les mesures de force, qui se comptent en heures.

## 6. Le second défaut, et pourquoi il est du même genre

`wasm/gammonnet.mjs` posait `efficiency = 0.566` en défaut de `rankPlays` et de
`cubeDecision`, dont le défaut d'`owner` est `0` = `GN_CUBE_CENTRED`. Or T34
(`docs/mesures/t34-efficacite.json`) mesure **0,688 centré / 0,566 possédé / 0,687 adverse** :
le seul défaut du dépôt servait l'efficacité du videau **possédé** à un videau **centré**.

Ce n'est pas resté sans conséquence. La valeur 0,688 a dû être **redécouverte par bissection**
contre un cas d'or, du côté de l'appelant, faute de pouvoir la lire ici — et la conclusion
tirée là-bas était qu'un défaut du build WebAssembly « n'est pas quelque chose à croire sans le
lire une seconde fois ». C'est la rétro-ingénierie que coûte un défaut inventé.

Le remède retenu n'est pas 0,566 → 0,688 mais **pas de défaut du tout**, comme en C : le
paramètre est exigé, et son absence lève une erreur qui nomme la constante à passer. Le prix de
la mesure est publié à côté — même position, même profondeur, seule l'efficacité change :

| efficacité | point de prise |
|---|---|
| 0,688 (centré, T34) | 0,726436 |
| 0,566 (possédé, l'ancien défaut) | 0,720610 |

**0,58 point de pourcentage sur le point de prise** : assez pour retourner un verdict à la
marge, jamais assez pour qu'un affichage ait l'air faux. Exactement le mode de défaillance que
`CLAUDE.md` §2 décrit.

## 7. Reproduire

```bash
make tie-census                                  # 0-ply, corpus T12, 21 lancers
make tie-census PLY=2 K=12 N=12                  # la forme canonique, 12 positions
make tie-census PLY=0 TIE_DUMP=1 > classement.txt  # le classement lui-même
make wasm-api                                    # dont l'invariant d'ordre des ex æquo
```

## Ce que ce correctif change pour qui épingle l'artefact

- **Aucun repère natif n'est à rejouer** : aucun classement natif ne bouge (§5). Le `qsort` de
  la glibc était stable en pratique ; c'est la cible WebAssembly, et elle seule, qui
  divergeait.
- **Une copie vendorisée ne reçoit le correctif qu'à la montée d'épingle suivante.** À cette
  montée, deux choses changent : le classement des ex æquo devient celui du natif, et
  `cubeDecision` **exige** désormais l'efficacité au lieu d'en inventer une.
- **Passer l'efficacité explicitement était déjà la bonne pratique** ; l'exiger ne casse donc
  que le code qui s'en remettait au défaut — c'est-à-dire précisément celui qui était faux.

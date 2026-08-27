# gammonNet — brief technique

> Ce document est **auto-suffisant**. Quelqu'un qui arrive sur ce dépôt sans autre contexte doit
> pouvoir travailler à partir de lui seul. Tout ce qui y est affirmé est soit sourcé, soit
> explicitement marqué comme hypothèse à mesurer.

## 1. Mission

Produire un **évaluateur de positions de backgammon** — réseau de neurones et recherche — qui
tourne **dans le navigateur** à 2-ply, et **en natif** aux profondeurs supérieures et en
rollout.

**Critère de succès, non négociable** : atteindre un niveau **équivalent ou supérieur à GNU
Backgammon et à eXtreme Gammon**, et pouvoir le **justifier par une mesure reproductible** dont
chaque source est traçable. « Équivalent » n'est pas une appréciation : c'est un nombre issu du
protocole décrit en §5.

**Contrainte de licence, non négociable** : tout artefact **distribué** — moteur, poids, tables —
est sous licence permissive, sans clause d'usage. Voir §3.

## 2. Prérequis d'environnement

- **Un compilateur C/C++17** (GCC ou Clang) et **Emscripten** pour la cible WebAssembly.
- **Python 3.10 ou plus**, avec PyTorch et NumPy, pour l'entraînement et la mesure. Sur les
  distributions dont le Python système est plus ancien (RHEL 8 et dérivés livrent 3.6), passer
  par un module AppStream (`python3.12`) et un environnement virtuel, sans toucher au Python
  système.
- **`gnubg-nn`** (`pip install gnubg-nn`) pour l'oracle de mesure.
- **Une machine multi-cœurs.** La génération de parties en self-play est **CPU-bound** et se
  parallélise linéairement ; c'est elle qui dimensionne les phases 0, 1 et 4.
- **Un GPU CUDA**, utile mais non requis pour les phases 0 à 3. Voir §4 pour ce qu'il apporte
  réellement — et ce qu'il n'apporte pas.

### Amorçage

```bash
python3.12 -m venv ~/venv-gammonnet && source ~/venv-gammonnet/bin/activate
pip install --upgrade pip torch numpy gnubg-nn

git clone https://github.com/alexstrehl/backgammon-ai-engine.git
cd backgammon-ai-engine
cd c_engine && bash build_unix.sh && cd ..      # ~20x plus rapide que le Python pur
python play_models.py --model1 best_models/cubeless_prob5_512_512_256_128.pt \
    --gnubg --game-mode cubeless-money --games 1000
```

## 3. Les sources, et ce qu'elles permettent

### 3.1 Le modèle de référence — `alexstrehl/backgammon-ai-engine`

<https://github.com/alexstrehl/backgammon-ai-engine> — **licence MIT**, poids inclus dans le
dépôt, code d'entraînement complet, moteur d'inférence C fourni (`c_inference/nn_eval.c`).

Entraîné **entièrement en self-play** ; GNU Backgammon n'y intervient que comme instrument de
mesure (`gnubg_eval.py`). Le modèle est donc exempt de toute dépendance sous copyleft.

Force annoncée par son auteur (10 M parties, IC 95 % bootstrap) :

| | vs GNU Backgammon | PR XG++ |
|---|---|---|
| 0-ply | +57,8 mEq/partie [+56,1 ; +59,6] | 1,06 [1,01 ; 1,11] |
| 1-ply vs 1-ply | +47,1 mEq/partie [+38,3 ; +56,0] | 0,50 [0,46 ; 0,53] |
| 2-ply vs 2-ply | +45,0 mEq/partie [+22,8 ; +67,3] | **0,22** [0,19 ; 0,25] |

**Modèle à retenir : `best_models/cubeless_prob5_512_512_256_128.pt`** (528k paramètres). Seul à
produire les **cinq probabilités** — gain, gain-gammon, gain-backgammon, perte-gammon,
perte-backgammon — indispensables au match play (§6). Les variantes `cubeful_money` sortent une
équité money agrégée, inutilisable en match.

### 3.2 Le moteur d'inférence — écrit ici

> **Tranché en T22 le 2026-08-03.** Un moteur d'inférence tiers a été évalué comme candidat, puis
> **écarté** : aucun code externe n'est embarqué. Motif complet dans
> [ADR-0001](docs/adr/0001-moteur-inference.md).

Le raisonnement tient en un chiffre. Le gain qu'on attendait d'une accumulation incrémentale de
type NNUE est **plafonné à 19 %** — c'est la part de la couche d'entrée dans les multiplications
de ce réseau, et c'est la seule chose que cette technique optimise. Un réseau d'échecs a le
rapport inverse, la couche d'entrée y écrasant tout le reste, d'où le gain spectaculaire là-bas et
son absence ici.

Les **×9 de débit** effectivement obtenus l'ont été autrement, dans notre propre code, sur des
causes indépendantes du moteur d'inférence : remplissage des lots à largeur fixe, regroupement des
passes d'élagage, compaction des entrées creuses. Voir `docs/mesures/`.

Ce que ce dépôt écrit lui-même : le codec de position, l'encodage des 196 caractéristiques, la
recherche expectiminimax 0→4 ply avec filtrage de coups, le réseau d'élagage, l'équité de match
dans la recherche, les tables de fin de partie, le portage WebAssembly et le pool de workers.

### 3.3 Les artefacts d'origine GNU Backgammon qui restent utilisables

**Les tables de fin de partie.** Reproductibles par la commande `makebearoff` de GNU Backgammon.
Ce ne sont **pas** des réseaux entraînés mais un **calcul exact** par programmation dynamique :
deux implémentations correctes produisent des fichiers identiques. C'est un fait mathématique,
pas une œuvre de création. Leur absence est un vrai trou de précision : sans table de fin de
partie, l'approximation apprise du réseau porte seule les courses pures et les bearoffs profonds,
et elle y est mesurablement plus faible qu'une table exacte. **Mesurablement** — donc mesuré :
0,00028 d'équité par décision de bearoff (T38).

**La table d'équité de match Kazaross-XG2.** Œuvre de **Neil Kazaross**, générée par rollouts XG
(jusqu'à 9 points) et GNU Backgammon Supremo (jusqu'à 15 points), étendue à 25 points par
projection des points de prise. GNU Backgammon n'en est que le véhicule de distribution.
[blunderDB](https://github.com/kevung/blunderDB), sous licence MIT, l'embarque déjà avec
attribution (`pkg/blunderdb/engine/met.go`). Au-delà de 25 points, le repli est le modèle de
Zadeh (*Management Science* 23, 986, 1977).

### 3.4 Ce qui est hors périmètre

Tout réseau publié sous une licence portant une **clause non commerciale** est hors du périmètre
de licence de ce dépôt, et n'est pas utilisé. La licence des **poids** doit être lue séparément de
celle du code qui les charge : un dépôt MIT peut parfaitement publier des modèles qui ne le sont
pas.

### 3.5 Récapitulatif des permissions

| Interdit | Motif |
|---|---|
| Poids GNU Backgammon, ou tout dérivé | GPL-3 ; servir au navigateur **est** une distribution |
| Copier du code GNU Backgammon dans le pipeline | Œuvre dérivée |
| Initialiser les poids depuis ceux de GNU Backgammon | Dérivé direct d'une œuvre GPL |
| Utiliser ou fine-tuner un réseau sous clause non commerciale | Hors du périmètre de licence de ce dépôt |
| Copier du code bgsage dans l'artefact | **MPL-2.0** (LICENSE du dépôt, vérifié le 2026-08-27 — et non AGPL-3 comme d'abord noté) : copyleft de fichier, qui imposerait ses obligations à l'artefact distribué. Lire, réimplémenter les idées et se comparer à son benchmark restent permis |

| Autorisé | Fondement |
|---|---|
| Lire le code et le manuel de GNU Backgammon | La GPL régit la distribution, pas la lecture |
| Faire tourner GNU Backgammon comme oracle de mesure | FSF, GPL FAQ : *« The output of a program is not, in general, covered by the copyright on the code of the program. »* |
| Réimplémenter des idées documentées (élagage, filtres de coups, classification contact/crashed/race) | Une idée n'est pas une œuvre |
| Utiliser les tables de fin de partie | Calcul exact reproductible |
| Utiliser la table Kazaross-XG2, avec attribution | Œuvre de N. Kazaross ; précédent MIT dans blunderDB |
| Utiliser et redistribuer les poids Strehl | MIT, poids inclus dans le dépôt |

## 4. La recette d'entraînement de référence

Publiée dans le README de `backgammon-ai-engine`, reproductible :

1. **TD(0) en ligne** sur un petit réseau (80 neurones cachés, 2 M épisodes), encodage Tesauro.
2. **Expansion progressive**, chaque étape repartant des poids précédents :
   `[80] → [150] → [150,150] → [256,256] → [512,512] → [512,512,256] → [512,512,256,256]`.
3. **Raffinement par backups de Bellman exacts** (dits « 1-ply ») : au lieu de
   `target = 1 − V(next)` sur un seul jet, `target = E_dés[max_coup(1 − V(next))]` sur les 21
   jets. Élimine la variance des dés du signal d'apprentissage. ~30× plus coûteux par épisode,
   donc réservé à la fin.
4. **Moteur C** pour la génération de parties (« ~20x faster training »), multiprocessing par
   `--workers`, GPU optionnel pour les phases larges.

Le cube en money est appris par renforcement en ajoutant simplement les actions (doubler,
prendre, passer) et quatre entrées binaires (`cube_centered`, `cube_own`, `cube_opponent_own`,
`is_cube_action`). Aucune formule de point de prise n'est utilisée.

Conclusion de l'auteur, à retenir : *« Simple RL techniques are sufficient to get a base-model
that is nearly as good as or better than gnubg's base-model. »*

### Ce qu'un GPU change — et ce qu'il ne change pas

**Il n'accélère pas beaucoup cette recette.** Deux raisons. Le goulot est la **génération de
parties** en self-play, qui tourne sur le moteur C et reste **CPU-bound** ; la rétropropagation
d'un réseau de 528k paramètres est négligeable devant elle. Et le README de référence est
explicite : *« GPU training is currently only supported for the 0-ply sampled backup mode »* —
le raffinement par backups exacts, le poste le plus coûteux, n'en bénéficie pas en l'état.

**Il n'autorise pas non plus un réseau beaucoup plus gros.** C'est le contresens à éviter : la
taille du modèle n'est pas limitée par la mémoire d'entraînement mais par le **navigateur**.
Doubler le nombre de paramètres double le coût de chaque évaluation, donc le coût du 2-ply chez
l'utilisateur, sur un budget déjà tendu (§6). **La contrainte de taille vient du client, jamais
de la machine d'entraînement.**

**Ce qu'il ouvre vraiment**, c'est ce que la recette de référence n'a pas fait, et que son auteur
désigne lui-même comme la suite : *« the next major avenue is evidently methods that search more
deeply and optimize the model for search (including MCTS and AlphaZero-like approaches). »* Il
observe en effet que son avantage sur GNU Backgammon **se réduit** avec la profondeur (+57,8
mEq/partie en 0-ply, +45,0 en 2-ply), et suggère que *« gnubg's base networks are more tuned for
deep search than ours »*.

Autrement dit : la piste la plus prometteuse n'est pas un plus gros réseau, c'est **un réseau du
même gabarit entraîné à être bon *sous* recherche** — en distillant les sorties d'une recherche
profonde dans le réseau lui-même.

## 5. Le protocole de mesure — à construire en premier

> **On ne peut pas entraîner ce qu'on ne sait pas mesurer.** Le harnais de mesure est le premier
> livrable, avant toute tentative d'amélioration du modèle.

**Round-robin** : chaque moteur affronte chaque autre ; la matrice complète se lit en **points
par partie** (ppg). Préféré à un classement parce qu'il n'existe pas d'étalon absolu au
backgammon, et parce qu'il révèle les **non-transitivités** (A bat B, B bat C, C bat A), qui
apparaissent réellement entre moteurs de styles différents.

**Participants minimum** : notre modèle et GNU Backgammon via `gnubg-nn`, plus autant de
références que possible. **Métriques** : ppg avec IC 95 % bootstrap, pourcentage de victoire, et
PR (rating de performance) si un analyseur externe est disponible. **Volume** : les chiffres
publiés reposent sur 10 M parties par paire ; en dessous d'environ 1 M, les écarts observés (de
l'ordre de 0,005 à 0,07 ppg) ne sont pas distinguables du bruit.

**Point de référence à reproduire** — le chiffre publié par l'auteur du modèle : **+57,8 mEq par
partie** contre GNU Backgammon, 0-ply, 10 M parties. C'est la seule référence externe que ce dépôt
cherche à reproduire, et T11 en rend compte.

*(Un round-robin public entre moteurs commerciaux a servi d'ordre de grandeur au tout début du
projet ; il a été retiré des références — le comparer à notre configuration mêlait des moteurs,
des profondeurs et des tables de fin de partie différentes, et n'éclairait rien.)*


où `colossus` est le modèle de §3.1 (`strehl_prob5_v26`), `xerxes` et `xg` des réseaux eXtreme
Gammon importés, `sage` bgsage stage 9. **Retrouver l'ordre de grandeur de la colonne `gnubg`
pour `colossus` (+0,067 ppg) est le premier jalon de vérification.**

## 6. La chaîne technique, bout à bout

Le chemin poids → navigateur est **déjà tracé** par le dépôt de référence. Il n'y a pas de pont
à inventer, seulement à emprunter.

### L'encodage des entrées — 196 caractéristiques

Documenté dans `encoding.py`. Toujours **du point de vue du joueur au trait** ; le réseau
apprend une fonction unique, `P(le joueur au trait gagne | plateau)`.

```
Bloc MOI (98)      : 24 points × 4 unités « thermomètre »  = 96
                     ma barre / 2,0                        =  1
                     mes pions sortis / 15,0               =  1
Bloc ADVERSAIRE(98): idem                                  = 98
                                                     Total = 196
```

Quand c'est Noir qui joue, les indices de points sont **miroités**, de sorte que « mon jan
intérieur » occupe toujours les mêmes positions dans le vecteur. Les modèles *cubeful* ajoutent
4 entrées binaires — **sans objet pour le modèle prob5 retenu**, qui est cubeless.

À comparer avec les 250/214 entrées de GNU Backgammon : ce n'est **pas** le même encodage. Un
modèle ne se transplante pas d'un moteur à l'autre.

### Le format de poids — `.bin`, magic `BGNN`

`export_weights.py` produit un binaire plat, lu par `c_inference/nn_eval.c` :

```
4 octets : magic "BGNN"
int32    : nombre de couches cachées
int32    : taille d'entrée
int32    : activation (0=relu, 1=sigmoid, 2=tanh, 3=leaky_relu, 4=hardsigmoid)
int32    : mode de sortie (0=probabilité, 1=équité, 2=prob5)
int32[]  : tailles des couches cachées
puis, par couche (cachées puis sortie) :
  float32[out × in] : matrice de poids (ordre ligne-majeur)
  float32[out]      : biais
```

En **mode prob5** (`output_mode = 2`), la couche de sortie a **5 neurones**. Le lecteur C
applique la sigmoïde, un **clamp d'événements imbriqués** (P(gain) ≥ P(gain-gammon) ≥
P(gain-backgammon)) puis la réduction en équité money.

**Point d'attention pour le match play** : cette réduction en équité money doit être
**contournable**. On a besoin des **cinq probabilités brutes** — c'est la table d'équité de
match qui fera la conversion, et elle a besoin de la distribution, pas d'un scalaire. Vérifier
l'ordre exact et la sémantique des cinq sorties dans `nn_eval.c` avant toute intégration : c'est
le genre de détail qui produit un moteur faux et silencieux.

### Le codec de position — le seul pont à construire

Les formats de position usuels (XGID, GNU Backgammon Position ID) doivent être convertis en un
vecteur de 196 flottants dans la convention ci-dessus. **Ce pont n'existe nulle part** : c'est le
premier morceau de code réellement neuf du dépôt.

Deux pièges :

- **L'orientation.** Une inversion de perspective ne fait pas planter : elle produit des
  évaluations plausibles et fausses. Se tester sur des positions asymétriques connues, jamais sur
  la position d'ouverture.
- **Le compte de pips comme sentinelle.** Vérification élémentaire de toute traduction de
  position : si le compte de pips ne correspond pas à la position voulue, tout ce qui suit est
  dépourvu de sens.

### Le match play n'ajoute rien à la recherche

Les réseaux sont *cubeless* et *aveugles au score* — ils sortent cinq probabilités, le score et
le cube n'entrent jamais dans le réseau. La conversion en équité de match se fait **après**, par
la table d'équité et la position du videau. C'est l'architecture de GNU Backgammon.

Une recherche 2-ply est donc **identique en match et en money** : pour chaque coup candidat,
énumérer les 21 jets de l'adversaire, trouver sa meilleure réponse, évaluer la position
résultante, moyenner (1/36 pour les doubles, 2/36 sinon). Le match n'intervient qu'à deux
endroits : la conversion finale, et — subtilité réelle à ne pas manquer — le fait que
l'adversaire, au niveau intermédiaire, doit choisir sa réponse en maximisant **son équité de
match**, pas son équité cubeless. À 4-away/2-away, un coup gammonesque ne vaut pas ce qu'il vaut
en money.

**Le filtrage de coups est ce qui rend le 2-ply praticable** : on n'évalue pas les ~20 coups
légaux à pleine profondeur, on garde les N meilleurs du niveau précédent. GNU Backgammon
documente ce mécanisme, ainsi que ses
[réseaux d'élagage](https://www.gnu.org/software/gnubg/manual/html_node/Pruning-neural-networks.html),
dans son manuel.

### La chaîne complète

```
best_models/cubeless_prob5_512_512_256_128.pt      (MIT)
        │  export_weights.py
        ▼
model.bin  (magic BGNN, float32 plat)
        │  c_inference/nn_eval.c  ──┬── gcc      → binaire natif (3-ply, rollouts)
        ▼                           └── emcc     → .wasm (navigateur, 2-ply)
5 probabilités
        │  + table d'équité de match  + tables de fin de partie  + recherche 2-ply
        ▼
équité de match, meilleur coup, décision de videau
```

### Le budget navigateur

> **⚠️ Cette section est celle du cadrage initial. Elle a été mesurée depuis, et les mesures
> l'ont remplacée.** Elle est conservée parce qu'une hypothèse dépassée fait partie du dossier :
> elle dit ce qu'on croyait, et de combien on se trompait.
>
> | | hypothèse de départ | **mesuré** |
> |---|---|---|
> | Pénalité WebAssembly | ×1,5 à ×2,5 | **×1,18 à ×1,29** |
> | Décision 0-ply | ~0,1 ms | **1,7 ms** |
> | Décision 2-ply | 245 ms | **1 394 ms** (filtre 1/1) |
> | Match de 7 points | 30 à 60 s | **~2 min** sur 3,3 workers mesurés |
>
> L'écart sur le 0-ply s'explique : les chiffres extrapolés venaient d'un moteur **NNUE à
> accumulation incrémentale** avec filtre de coups actif — ce n'est pas le même calcul. Le
> détail : [T21](docs/mesures/2026-08-03-T21-debit-navigateur.md),
> [T30](docs/mesures/2026-08-03-T30-recherche.md),
> [la décision navigateur](docs/mesures/2026-08-04-decision-navigateur.md).

Extrapolation à partir de débits publiés par un moteur tiers (un cœur de Ryzen 5 3600, filtre de
coups actif), avec une pénalité WebAssembly estimée entre ×1,5 et ×2,5 — **hypothèse, à mesurer en
phase 2** :

| Profondeur | Coût/décision (natif) | Match de 7 pts (~300 décisions), 4 workers |
|---|---|---|
| 0-ply | ~0,1 ms | instantané |
| 1-ply | 1,5 ms | ~1 s |
| **2-ply** | **245 ms** | **~30 à 60 s** |
| 3-ply | 2,3 s | ~6 à 12 min |

Lecture : **le 2-ply passe dans le navigateur** avec une barre de progression ; **le 3-ply ne
passe pas en interactif**. C'est ce qui fixe la cible du projet. Réserve : les chiffres 3-ply de
cette extrapolation étaient eux-mêmes qualifiés de très dispersés par leur auteur.

**La conclusion tient, les chiffres non.** Le 2-ply passe bien — mesuré à ~2 min par match de 7
points, sur desktop comme sur iPhone — mais **seulement avec un filtre agressif**, ce que cette
extrapolation ne laissait pas voir. Sans filtre, une décision 2-ply coûte ~3,8 millions
d'évaluations.

## 7. Attribution — condition de livraison

La licence MIT exige la notice de copyright *« in all copies or substantial portions of the
Software »*. **Un module WebAssembly servi au navigateur est une copie distribuée.** Toute brique
MIT embarquée doit donc être livrée avec :

- une entrée dans `THIRD-PARTY.md` : nom, auteur, licence, lien de source, et **ce qui est
  effectivement utilisé** ;
- la notice conservée dans l'artefact lui-même (bannière du build WebAssembly, ou fichier de
  licence servi à côté).

**Distinction obligatoire** : le moteur d'inférence et les poids peuvent venir de sources
différentes, et l'attribution doit le dire. Nommer un tiers sans préciser ce qu'on lui doit
laisserait croire qu'on emploie ses modèles — ce serait faux, et injuste envers lui comme envers
l'auteur du modèle réellement utilisé.

## 8. Nomenclature — ce qu'on a le droit de renommer, et ce qu'on ne devrait pas

MIT autorise la modification et la redistribution sans restriction, et **n'impose ni renommage ni
interdiction de renommer** — contrairement à BSD-3-Clause (non-endorsement) ou Apache-2.0 (§4b,
obligation de marquer les fichiers modifiés). Juridiquement, tout nom est permis.

**Mais le seuil qui compte est factuel : un réseau ne devient un autre réseau que si ses poids
changent.** Ni le couplage à une table de fin de partie (composant *à côté*, poids intacts), ni
la compilation en WebAssembly (format du **moteur**, pas du modèle), ni une conversion de format
ne produisent un modèle nouveau. Les rebaptiser reviendrait à s'attribuer ce qu'on n'a pas
produit — et coûterait exactement ce que le critère de succès exige : une provenance traçable.

Le seuil est franchi par un **entraînement supplémentaire**, un fine-tuning, ou un
réentraînement de zéro. Une quantification donne « X quantifié », pas « Y ».

**Nomenclature à trois niveaux** — le réseau garde le nom de son auteur, la configuration porte
le nôtre :

| Niveau | Forme | Qui nomme |
|---|---|---|
| **Réseau** (les poids) | `strehl-prob5-512-512-256-128` | conserve la paternité de l'auteur |
| **Configuration** (réseau + recherche + fins de partie + équité de match) | `gammonNet 2-ply` | nous |
| **Affichage** | « 2-ply · sur votre appareil » | nous |

## 9. Pièges connus

- **Attendre la vitesse d'une accumulation NNUE** (§3.2) — elle ne porte que 19 % du calcul de ce
  réseau, et un mode dense la désactive de toute façon. Ne pas investir là pour de mauvaises
  raisons : les ×9 obtenus l'ont été ailleurs.
- **Confondre le dépôt public d'un moteur et le produit** — un dépôt public est souvent le cœur
  d'évaluation **dépouillé** du packaging navigateur, du filtrage de coups et des tables de fin de
  partie. Les chiffres de débit publiés décrivent le produit, pas le dépôt.
- **Le trou des fins de partie** — un réseau seul est mesurablement plus faible qu'une table
  exacte en course et en bearoff profond. Ne pas conclure sur la force globale à partir d'un
  corpus qui en contient beaucoup ; les positions de contact sont la comparaison honnête.
- **Le volume de mesure** — en dessous d'environ 1 M parties par paire, les écarts entre bons
  moteurs ne sortent pas du bruit.
- **La pénalité WebAssembly** — estimée entre ×1,5 et ×2,5. **C'est une hypothèse, pas une
  mesure.** Toute la frontière 2-ply / 3-ply en dépend.
- **Le silence d'un modèle faux** — un réseau à qui l'on donne une entrée qu'il n'a jamais vue
  retourne cinq probabilités parfaitement plausibles. Un moteur peut ainsi se tromper d'une
  demi-unité d'équité sur une fraction notable des positions sans aucun signe extérieur. D'où la
  règle : un modèle qu'un build ne sait pas évaluer est **refusé, jamais approximé**.

## 10. Sources

- `alexstrehl/backgammon-ai-engine` — <https://github.com/alexstrehl/backgammon-ai-engine> (MIT)
- Manuel GNU Backgammon, réseaux d'élagage —
  <https://www.gnu.org/software/gnubg/manual/html_node/Pruning-neural-networks.html>
- FSF, GPL FAQ, *output of a GPL program* —
  <https://www.gnu.org/licenses/gpl-faq.html#WhatCaseIsOutputGPL>
- `wildbg` (comparaison) — <https://github.com/carsten-wenderdel/wildbg> (Apache-2.0/MIT), plus
  faible : son README annonce *« an error rate of roughly 5.9 for 1-pointers »*
- `blunderDB` (précédent MIT pour la table d'équité de match) —
  <https://github.com/kevung/blunderDB>

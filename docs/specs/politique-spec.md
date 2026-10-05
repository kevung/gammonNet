# La politique de jeu sans état — spécification

> **Statut** : spécification d'implémentation, écrite avant le code le 2026-10-05. L'implémentation
> (`src/gn_policy.h`, `src/gn_policy.c`) la suit à la lettre ; tout écart est un bug ou une
> révision de ce document, jamais une improvisation silencieuse.
>
> **Ce qu'elle ajoute au périmètre.** Jusqu'ici : *une position entre, une évaluation sort.*
> Désormais aussi : **une décision entre, une action sort** — toujours ni partie ni appelant.
> La partie, les dés, le score, l'historique et l'horloge restent chez qui appelle. La fonction
> ne garde rien d'un appel à l'autre : deux appels identiques rendent la même action, bit pour
> bit, quel que soit l'ordre dans lequel on les fait.

## 1. Pourquoi une fonction et non un moteur de partie

Faire jouer un match entier demande cinq réponses, que la bibliothèque savait déjà calculer
séparément (`gn_best_play`, `gn_search_probs`, `gn_cube_decide`) mais qu'un appelant devait
recomposer lui-même — avec les conventions de référentiel, de propriétaire du videau, de score
vu du trait, d'efficacité par état de videau, et les gardes de videau mort que T35 a dû ajouter
à sa boucle après coup. Chaque recomposition est une occasion de se tromper silencieusement :
la campagne T35 en a payé une (`classify_gnubg_verdict`, 4,9 jours de calcul à refaire).

La composition est donc écrite **une fois, ici**, là où elle se mesure. Elle n'introduit aucun
calcul nouveau : chaque nombre qu'elle rend vient d'une fonction déjà exportée et déjà mesurée.
La seule pièce neuve est la **réponse du preneur** (§5.3) et la **lecture exacte de la défaite
certaine** (§5.5).

## 2. L'entrée — `GnDecision`

**Un seul référentiel : celui du joueur au trait.** `position.turn` désigne le joueur au trait ;
le score (`away_on_roll`, `away_opponent`) et le propriétaire du videau (`cube_owner`,
`GnCubeOwner`) sont vus de lui, exactement comme dans `GnSearchConfig`. Celui qui **décide** se
déduit de ce qui est en attente (§3) ; l'appelant n'a jamais à retourner quoi que ce soit.

| champ | sens |
|---|---|
| `position` | la position, `turn` = le joueur au trait |
| `pending` | ce qui est en attente (§3) |
| `d1`, `d2` | le lancer, 1..6, lu seulement si `pending == GN_PENDING_MOVE` |
| `cube` | valeur du videau, 1, 2, 4, … (money comme match) |
| `cube_owner` | `GN_CUBE_CENTRED`, `GN_CUBE_OWNED` (au trait), `GN_CUBE_OPPONENT` |
| `jacoby` | règle de Jacoby, money seulement (sans effet en match, comme `gn_cube_decide`) |
| `use_match` | 0 money, 1 match |
| `away_on_roll`, `away_opponent`, `crawford` | l'état de match, vu du trait (`GnMatchState`) |
| `resign_value` | 1, 2 ou 3 : la valeur offerte, lue seulement si `pending == GN_PENDING_RESIGN` |

Le niveau est un **nom** : `instant`, `normal`, `thorough` — ceux de `gn_search_level`, et
aucun autre (§4).

## 3. Ce qui peut être en attente, et qui décide

| `pending` | situation | décideur | actions possibles |
|---|---|---|---|
| `GN_PENDING_MOVE` | dés lancés | le joueur au trait | `GN_ACTION_MOVE` |
| `GN_PENDING_CUBE` | avant de lancer | le joueur au trait | `GN_ACTION_RESIGN`, `GN_ACTION_DOUBLE`, `GN_ACTION_ROLL` |
| `GN_PENDING_TAKE` | le joueur au trait vient de doubler | son adversaire | `GN_ACTION_TAKE`, `GN_ACTION_PASS` |
| `GN_PENDING_RESIGN` | le joueur au trait offre d'abandonner | son adversaire | `GN_ACTION_ACCEPT`, `GN_ACTION_REJECT` |

L'abandon du joueur (cas 5 de l'issue) n'a pas d'état d'attente propre : c'est une réponse
possible **avant de lancer**, examinée en premier (§5.2). Un abandon ne se propose jamais une
fois les dés lancés : qui a perdu à coup sûr l'a déjà su avant de lancer.

`GN_PENDING_TAKE` et `GN_PENDING_RESIGN` gardent le joueur au trait comme référentiel parce que
c'est **lui** qui est au trait de la position évaluée : la distribution avant le jet se calcule
de son point de vue, puis se retourne pour le décideur.

## 4. Les niveaux

Un niveau est **la forme d'une recherche** : `gn_search_level(name)` — profondeur, filtre en
triplet, élagage. La politique s'en sert à l'identique pour les coups **et** pour la
distribution qui alimente les décisions de videau et d'abandon : le videau se décide au ply du
niveau, avec le même filtre. Un nom inconnu est refusé.

Un niveau qui élague (`prune_k > 0`, le niveau `normal`) **exige** le réseau d'élagage : sans
lui l'appel est refusé, jamais rabattu sur la recherche non élaguée — ce serait une autre
configuration que celle que le nom annonce, la même règle que `GammonNetCubePlayer._load`.

**L'efficacité du videau n'est pas une entrée.** Elle est celle mesurée par T34
(`docs/mesures/t34-efficacite.json`), indexée par l'état du videau **vu du décideur** :
centré 0,6880000000000001, possédé 0,5660000000000001, adverse 0,687 — les doubles que la boucle
T35 lisait dans ce fichier, à l'ulp près. Un test les relit dans la mesure.

## 5. Les cinq cas

### 5.1 Dés lancés → le coup

- Aucun coup légal : `GN_ACTION_MOVE` avec `play.num_moves == 0` et `play.result` = la position,
  trait passé. Pas de recherche.
- Un seul coup légal : celui-là, pas de recherche (`searched == 0`).
- Sinon : `gn_best_play` au niveau, **cubeless** — money, ou table de match au score
  (`gn_search_config_match` avec le videau courant). C'est le joueur de pions de T35, et c'est
  pour cela qu'il est retenu : la valuation cubeful des feuilles (`use_cube`) n'a jamais été
  mesurée comme joueur de match ; l'adopter ici affirmerait une force sans mesure.

`equity_a` rend l'équité du coup retenu sur l'échelle de la recherche (money cubeless, ou
`2·MWC − 1`), du point de vue du joueur ; `equity_b` vaut 0.

### 5.2 Avant de lancer → abandonner, doubler ou lancer

Dans l'ordre :

1. **Défaite certaine** (§5.5) : `GN_ACTION_RESIGN` avec sa valeur certaine. Aucune recherche.
2. **Videau indisponible** → `GN_ACTION_ROLL`, **aucun calcul** :
   - le videau appartient à l'adversaire (`cube_owner == GN_CUBE_OPPONENT`) ;
   - match : partie de Crawford ;
   - match : videau mort pour le joueur au trait, `cube >= away_on_roll` — gagner cette partie
     lui donne déjà le match, doubler n'a aucun gain et seulement un risque. Couvre aussi le
     videau mort des deux côtés. C'est la garde que T35 a dû ajouter à sa boucle
     (`docs/mesures/2026-08-26-T35-verdict.md`, défaut résiduel) ; elle vit désormais ici.
3. **Le verdict de videau au ply du niveau**, exactement le chemin de T35 :
   - money, et la table bilatérale exacte installée (`gn_bearoff_shared`) connaît la position :
     `gn_cube_verdict(e_nd, 2·E_adverse, 1)` sur les équités exactes de la table (`e_nd` =
     l'équité centrée ou possédée selon `cube_owner`) ;
   - sinon : `gn_search_probs` au niveau, puis `gn_cube_decide` à l'efficacité de l'état du
     videau du joueur au trait, `jacoby` transmis.
   - **Double** sur `GN_DOUBLE_TAKE` et `GN_DOUBLE_PASS`. **Pas de double** sur
     `GN_NO_DOUBLE`, sur `GN_TOO_GOOD`, et sur un **double optionnel** : un verdict
     `GN_DOUBLE_PASS` dont l'équité de double **égale** celle de ne pas doubler
     (`e_double == e_nd`). Doubler n'y gagne rien ; ne pas doubler garde le videau. C'est
     l'égalité au sommet de l'échelle que T35 a trouvée sur les bearoffs à P(gain) = 1 — la
     seule différence d'action avec la boucle de T35, et elle est sans coût d'équité par
     définition.

`equity_a` = ne pas doubler, `equity_b` = doubler (`min(prise, passe)`), du point de vue du
joueur au trait, par unité du videau courant en money, en MWC en match — les champs de
`GnCubeDecision` tels quels. Nuls quand rien n'a été calculé.

### 5.3 Double reçu → prendre ou passer — **la fonction qui manquait**

`gn_cube_decide` rend un verdict du point de vue du doubleur ; il ne dit pas ce que le preneur
fait **avec sa propre efficacité**. La réponse du preneur compare les deux branches **vues du
preneur** :

- `passer` vaut, pour le preneur, `−1` par unité du videau courant en money, et
  `2·MWC_après(perte de cube) − 1` en match (`gn_met_after`) ;
- `prendre` vaut l'opposé de la valeur, pour le doubleur, de la position au videau **doublé**
  possédé par le preneur : `−2·gn_cube_equity(OPPONENT, 1, x)` en money,
  `−gn_cube_value(OPPONENT, état au videau doublé, x)` en match. `x` est l'efficacité de l'état
  « adverse » **vu du doubleur** (0,687) — l'indexation de la boucle T35, celle qui a été
  mesurée ; la distribution est celle du doubleur au trait, au niveau.
- Money, table exacte installée et position dans son domaine : prendre vaut `−2·E_adverse`
  exact.

**Prendre si et seulement si prendre vaut strictement plus que passer** pour le preneur. Une
égalité passe — comme T35 (`e_dt < e_dp`).

Refusé (−1) : un double que les règles interdisent — videau chez le preneur
(`cube_owner == GN_CUBE_OPPONENT`, vu du doubleur), ou partie de Crawford.

`equity_a` = prendre, `equity_b` = passer, du point de vue du preneur : points par videau
courant en money, MWC du preneur en match (`(1 − e)/2` des nombres du doubleur, sur l'échelle
`2·MWC − 1` de `gn_cube_value`). Le verdict, lui, est la comparaison de T35 sur les nombres du
doubleur, telle quelle.

### 5.4 Abandon proposé → accepter ou refuser

Le décideur compare ce que l'abandon lui rapporte à ce que vaut **continuer sans videau** :

- la distribution avant le jet, au niveau, du point de vue du joueur au trait (celui qui
  abandonne), retournée pour le décideur ;
- money : continuer vaut l'équité cubeless `gn_money_equity` — sous Jacoby avec videau centré,
  gammons et backgammons ne comptent pas, donc `2p − 1` ; l'abandon vaut `resign_value` ;
- match : continuer vaut `gn_match_winning_chance` à l'état courant, vu du décideur ;
  l'abandon vaut `gn_met_after(gain de resign_value · cube)`.

**Accepter si l'abandon vaut au moins autant** (`>=`) : on n'y perd rien. Le videau est
ignoré à dessein, comme le demande l'issue : sa valeur d'option est la seule chose qu'un
abandon accepté abandonne, et elle n'a pas de signe garanti.

`equity_a` = accepter, `equity_b` = continuer, du point de vue du décideur (points par
videau en money ; MWC en match).

### 5.5 Abandon du joueur → seulement la défaite certaine, pour sa valeur certaine

**Une lecture exacte, jamais un jugement d'équité.** Le réseau ne participe pas.

Domaine : **une course sans contact** — aucun pion sur la barre, et chaque pion du joueur au
trait a dépassé chaque pion adverse. Hors de ce domaine, on n'abandonne jamais.

En course, les deux camps sont indépendants, et la question devient : *en combien de jets
chacun peut-il, au mieux et au pire, atteindre un but ?* Avec `H = 2` jets d'horizon :

- `peut(camp, but, k)` : il existe une suite de lancers et de coups qui atteint le but en au
  plus `k` jets (∃ lancer, ∃ coup) ;
- `sûr(camp, but, k)` : quels que soient les lancers, un coup atteint le but en au plus `k`
  jets (∀ lancer, ∃ coup).

Le joueur au trait joue le premier. Pour `k = 1..H`, la **défaite est certaine** si
`¬peut(joueur, tout sortir, k) ∧ sûr(adversaire, tout sortir, k)`. Alors, avec `k` ce plus
petit horizon :

- **simple certain** si le joueur a déjà sorti un pion, ou s'il est `sûr` d'en sortir un en
  1 jet (l'adversaire ne peut pas finir avant que le joueur ait lancé une fois) ;
- **gammon certain** si le joueur n'a rien sorti, ne `peut` pas en sortir un en `k` jets, et
  n'a aucun pion dans le jan adverse ni sur la barre — ou s'il en a et est `sûr` de les en
  sortir en 1 jet ;
- **backgammon certain** si gammon certain et le joueur ne `peut` pas sortir du jan adverse en
  `k` jets.

La valeur est certaine si exactement une de ces trois lectures l'est ; sinon, pas d'abandon.
**Jacoby** (money, videau centré) : une partie dont le videau n'a pas tourné vaut un point,
donc la valeur certaine est 1.

L'horizon borne le coût, il ne rend jamais une réponse fausse : au-delà, la défaite n'est
simplement pas lue, et l'on joue. `H` est une constante nommée ; l'élargir est un choix mesuré.

## 6. La sortie — `GnAction`

| champ | sens |
|---|---|
| `kind` | l'action (§3) |
| `play` | `GN_ACTION_MOVE` : le coup ; ailleurs, zéro |
| `resign_value` | `GN_ACTION_RESIGN` : 1, 2 ou 3 ; ailleurs 0 |
| `searched` | 1 si une recherche ou une évaluation a tourné, 0 pour les raccourcis |
| `equity_a`, `equity_b` | les deux nombres comparés, §5, du côté du décideur ; 0 quand rien n'a été calculé. **Une échelle par mode** pour les décisions de videau et d'abandon : points par videau courant en money, MWC en match. Le coup (§5.1) garde l'échelle de la recherche |

Retour : 0, ou −1 pour une entrée refusée — position invalide ou terminée, dés hors 1..6, niveau
inconnu, élagage exigé et absent, état de match hors table (`gn_match_state_is_valid`),
`resign_value` hors 1..3, double interdit (§5.3). **Refusé, jamais approximé.**

## 7. Hors périmètre

Beaver et raccoon comme actions (`gn_cube_decide_ex` reste là pour les analyser) ; toute
réflexion pendant le tour adverse ; un niveau au-dessus de `thorough` ; les niveaux affaiblis ;
le plafond money du videau (une règle de séance : qui l'applique ne demande pas) ; la
valuation cubeful des feuilles pour le choix du coup (non mesurée comme joueur de match, §5.1).

## 8. Le corpus de référence — `data/policy_reference.bin`

Un export canonique (`CONTEXT.md`) : ce que la référence C répond pour chaque décision, figé,
pour qu'un portage se vérifie contre la référence au lieu de contre lui-même. Généré par
`tools/policy_corpus.py` ; un test le rejoue sur le build par défaut et exige l'égalité **octet
pour octet**.

**Conditions de génération** (et donc de rejeu) : build natif par défaut (pas `NATIVE_FP`),
poids `models/cubeless_prob5_512_512_256_128.bin` et `models/prune_32.bin` — leurs empreintes
SHA-256 sont dans `data/policy_reference.json` —, **aucune table bilatérale installée** (la
politique suit alors le modèle partout, ce qu'un portage sans la table de 1,2 Gio reproduit).

Petit-boutiste, sans remplissage implicite :

```
en-tête, 16 octets
  0   4  magic "GNPL"
  4   4  u32 version = 1
  8   4  u32 count
 12   4  u32 record_size = 160

enregistrement, 160 octets
  entrée (80 octets)
  0  24  i8[24]  points (convention gn_rules.h : + blanc, − noir, indice 0 = point 1 de blanc)
 24   2  u8[2]   bar[blanc], bar[noir]
 26   2  u8[2]   off[blanc], off[noir]
 28   1  u8      turn (0 blanc, 1 noir) — le joueur au trait
 29   3  zéro
 32   4  i32 level        0 instant, 1 normal, 2 thorough
 36   4  i32 pending      GnPending
 40   4  i32 d1
 44   4  i32 d2
 48   4  i32 cube
 52   4  i32 cube_owner   GnCubeOwner, vu du trait
 56   4  i32 jacoby
 60   4  i32 use_match
 64   4  i32 away_on_roll
 68   4  i32 away_opponent
 72   4  i32 crawford
 76   4  i32 resign_value
  sortie (80 octets)
 80   4  i32 rc           0, ou −1 (refus : le reste de la sortie est nul)
 84   4  i32 kind         GnActionKind
 88   4  i32 resign_value
 92   4  i32 searched
 96   4  i32 num_moves    0..4
100   8  i8[4][2]        (from, to) par sous-coup ; GN_BAR = −1, GN_OFF = −2 ; zéro au-delà
108  29  la position résultante (même agencement que l'entrée), zéro hors GN_ACTION_MOVE
137   3  zéro
140   8  f64 equity_a
148   8  f64 equity_b
156   4  zéro
```

L'**action** (kind, valeur, coup, position résultante) doit être reproduite exactement. Les
**équités** sont les doubles de la référence, bit pour bit ; un portage qui ne refait pas
l'arithmétique dans le même ordre les compare à sa propre tolérance — c'est à lui de la mesurer,
pas à ce fichier de la promettre.

## 9. La mesure

La boucle de match de T35 (`python/gammonnet/cubeful.py`, `bench/run_t35.py`), rejouée avec
cette politique pour notre camp, contre gnubg au même réglage que T35, doit retrouver le résultat
de T35 dans son intervalle : **50,42 % [50,16 ; 50,69]** de MWC sur 50 000 paires
(`docs/mesures/2026-08-26-T35-verdict.md`).

Deux contrôles, parce que l'un est rapide et l'autre ne l'est pas :

1. **L'identité.** À un même réglage, la politique doit prendre **exactement** les décisions
   du joueur de T35 (`GammonNetCubePlayer`), sauf le double optionnel (§5.2) : comparée
   décision par décision sur des parties jouées, et en paires dupliquées politique contre joueur
   T35, qui doivent totaliser exactement zéro. C'est la preuve que la composition n'a rien
   changé à ce que T35 a mesuré ; elle ne dépend pas de la profondeur, qui n'entre que par la
   configuration transmise, et se vérifie donc aussi à bas coût à 0-ply.
2. **Le niveau `normal` en match contre gnubg**, protocole T35 inchangé (longueur 7, scores
   échantillonnés, graine `20260810`) : un échantillon dimensionné, son intervalle, et la
   compatibilité avec celui de T35. Le niveau `normal` diffère du réglage de T35 par le seul
   filtre racine en triplet (+0,00007 [+0,00002 ; +0,00012] d'équité par décision, mesuré) :
   indiscernable à tout volume raisonnable d'un match.

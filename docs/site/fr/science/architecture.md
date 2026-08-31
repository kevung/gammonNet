# L'architecture, et pourquoi chaque brique existe

Un évaluateur de backgammon n'est pas un réseau de neurones. C'est **cinq composants** dont chacun
comble un déficit que les autres ne peuvent pas combler.

## 1. L'encodage : 196 caractéristiques

Une position devient un vecteur de 196 nombres. C'est le format que le réseau réutilisé attend, et
le **goulot du projet** : une erreur y est silencieuse et contamine toutes les mesures suivantes.

Le codec a donc été validé position par position contre un générateur indépendant avant que quoi
que ce soit d'autre soit écrit.

```{admonition} Un fait qui compte pour la suite
:class: note

**Le vecteur est presque vide** : 26,0 entrées non nulles sur 196 en moyenne (mesuré sur 4 000
positions de vraie partie), et 38,3 pour l'**union** d'une fratrie de 32 coups — les frères ne
diffèrent que d'un coup, leurs entrées se recouvrent presque.

C'est ce fait qui a permis un gain de vitesse exact plus tard (voir [](optimisations)).
```

## 2. Le réseau : 196 → 512 → 512 → 256 → 128 → 5

Cinq sorties, **imbriquées** : P(gain), P(gammon gagné), P(backgammon gagné), P(gammon perdu),
P(backgammon perdu). Les poids sont ceux d'**Alexander Strehl** (MIT), entraînés en self-play, et
n'ont **pas** été réentraînés — la paternité leur reste.

Le réseau est **cubeless** et **aveugle au score** : il ne sait rien du videau ni du match. Tout ce
qui suit existe pour combler cela.

## 3. La recherche expectiminimax : 0 à 4 plies

```
V(pos, 0) = équité money cubeless de pos, du point de vue de pos.turn
V(pos, k) = Σ sur les 21 jets  w(jet) × max sur les coups ( −V(résultat, k−1) )
```

Les poids valent 1/36 pour un double et 2/36 sinon — et un test le vérifie plutôt que de le
supposer.

```{admonition} La négation, qui se trompe en silence
:class: warning

`GnPlay.result` a déjà **rendu la main**. La valeur d'un coup, pour celui qui le joue, est donc la
**négation** de ce que le réseau répond sur la position résultante. L'inverser ne produit ni
plantage ni avertissement : le moteur joue le meilleur coup de son adversaire, avec une confiance
totale.

Chaque négation du code est là pour cette raison, et chacune est commentée.
```

**Le filtrage de coups** rend le 2-ply praticable : seuls les `filter[d]` meilleurs candidats d'un
pré-tri superficiel sont recherchés en profondeur. Ce que le filtre coûte est **mesuré**, jamais
supposé.

**L'équivalence des profondeurs avec GNU Backgammon est mesurée**, pas supposée — voir
[](pr).

## 4. L'équité de match

Le réseau étant cubeless, jouer au score demande une **table d'équité de match** : la table
Kazaross-XG2, œuvre de Neil Kazaross, avec attribution.

```{admonition} La subtilité invisible en money
:class: important

Au niveau intermédiaire d'une recherche, **l'adversaire maximise son équité de match**, pas son
équité cubeless. À 4-away/2-away, un coup gammonneux ne vaut pas ce qu'il vaut en money.

Un 2-ply qui maximiserait l'équité cubeless au niveau intermédiaire est **faux en match** — et
**aucun test money ne le dirait jamais**.
```

La recherche bascule donc l'état de match à chaque ply, et travaille en équité de match
`2·MWC − 1` plutôt qu'en MWC brute : sur cette échelle la valeur de l'adversaire reste la
**négation**, exactement comme en money, et toutes les négations du code restent justes.

## 5. Le videau

Le modèle de décision est celui de Janowski, à **efficacité mesurée** — jamais empruntée à une
constante publiée. Trois efficacités, une par état de possession du videau (centré, possédé,
adverse) : 0,688 / 0,566 / 0,687, ajustées sur nos propres données.

Le videau agit à deux endroits :

- **La décision** de doubler, prendre ou passer.
- **Le choix du coup** : la valuation *cubeful* des feuilles rend le jeu audacieux vers
  l'encaissement quand on possède le videau, sobre quand on l'a contre soi. Vérifié : la même
  position vaut −0,167 avec le videau en main et −0,449 avec le videau contre soi.

## 6. Les tables exactes de fin de partie

En fin de partie, il n'y a plus rien à estimer : la valeur est **calculable exactement**. La table
bilatérale de GNU Backgammon donne les équités cubeful exactes dans son domaine.

**Ce qu'elle comble est chiffré** : 0,00028 d'équité par décision de bearoff, là où GNU Backgammon
consulte la sienne et n'y perd rien. Le pire cas mesuré au 1-ply vaut 0,0919 sur une seule
décision — **c'est la queue, pas la moyenne, qui coûte**.

```{admonition} Elle ne se distribue pas
:class: warning

La table pèse **1,2 Gio**. Aucun artefact web ne la transporte. Le moteur publié retombe donc sur
le réseau en fin de partie, au coût mesuré ci-dessus. C'est une limite réelle, pas un oubli.
```

## Le réseau d'élagage

Un sixième composant, distillé de **notre propre réseau** — jamais de GNU Backgammon : un réseau
196 → 32 → 5, 92,5× moins cher par évaluation, qui **trie** les coups pour que le grand n'en note
qu'une poignée. Ce qu'il coûte en qualité est mesuré ([](optimisations)).

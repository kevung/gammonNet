# La force : la campagne T35

## Le protocole

**Configuration complète** — réseau, recherche 2-ply filtrée `(0,1,3)`, équité de match, tables
exactes de fin de partie, videau 2-ply — contre **GNU Backgammon au même réglage** : 2-ply, filtre
`(0,1,3)`, videau 2-ply, `prune = 1` (son jeu réel).

Dés communs, paires dupliquées, graine 20260810, bootstrap sur les paires.

## Le résultat

| Moitié | Volume | Mesure | IC 95 % |
|---|---|---|---|
| **money** cubeful | 50 000 paires | **−0,0119 ppg** | [−0,0310 ; +0,0074] |
| **match**, 7 points | 50 000 paires | **50,42 % de MWC** | [50,16 ; 50,69] |

En match, victoires nettes par match : +0,0085 [+0,0032 ; +0,0138].

## Le verdict, dans les termes exacts

- **Équivalent : confirmé.** En money l'IC contient zéro ; en match, 50,42 % de MWC.
- **Supérieur : non établi.** L'écart de +0,0400 ppg mesuré en *cubeless* ne se reproduit pas une
  fois le videau branché.
- **eXtreme Gammon : non mesuré.** Aucun oracle XG n'existe dans ce dépôt.

## Ce que la campagne a coûté

7 051 minutes à 30 ouvriers pour la moitié match — 4,9 jours. 11 776 886 tours joués, 241 908
doubles, **0 partie bloquée**.

## Une campagne perdue, et pourquoi elle est racontée ici

**La première moitié match était invalide et a été jetée.** Elle donnait 56,4 % de MWC contre
l'égalité — tout l'écart concentré là où le videau vit, culminant à 60,3 % en post-Crawford.

La cause : `classify_gnubg_verdict` lisait *« Never redouble, take (dead cube) »* comme un double.
La campagne faisait donc **redoubler GNU Backgammon exactement là où il dit de ne jamais le
faire**.

```{admonition} La signature était dans le journal, sans qu'on la cherche
:class: note

**84,1 % des paires post-Crawford atteignaient un videau de 4 ou 8**, là où le jeu correct plafonne
à 2. Après correction : **2,2 %**, et le videau 8 disparaît entièrement.

Et la géographie de l'écart s'est inversée avec : l'avantage n'est plus concentré en post-Crawford
(+0,0099 par match hors Crawford, −0,0020 dedans).
```

Le journal invalide est **conservé** comme pièce à conviction, et marqué : aucun chiffre n'en sort.

## Un défaut résiduel, chiffré et nommé

Il reste 131 paires (0,26 %) où le videau atteint 4 en post-Crawford. Rejeu instrumenté de trois
d'entre elles : **trois fois nous, zéro fois gnubg**.

L'enquête a montré que **le coût en équité est exactement zéro** : les positions fautives sont
toutes des bearoffs à P(gain) = 1,0, où `gn_cube_verdict` tranche une égalité au sommet de
l'échelle vers « double ». Un gain certain reste certain à n'importe quel videau.

Une première version de cette fiche affirmait que le défaut « jouait contre nous ». **C'était
faux**, et la correction est consignée plutôt qu'effacée.

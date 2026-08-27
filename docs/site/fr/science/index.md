# Documentation scientifique

```{toctree}
:maxdepth: 2

architecture
protocole
force
pr
match
optimisations
limites
reproduire
```

## À qui s'adresse ce volet

À qui veut **juger** ce moteur plutôt que l'utiliser. Il est écrit pour être lu par quelqu'un qui
ne nous croit pas, et il est organisé pour qu'on puisse le contredire : chaque affirmation chiffrée
porte son protocole, son volume, son intervalle de confiance, et la commande qui la reproduit.

## La question, telle qu'elle a été posée

> Un évaluateur de positions de backgammon d'un **niveau équivalent ou supérieur à GNU Backgammon
> et eXtreme Gammon**, distribuable dans un navigateur, et dont toute affirmation de force est
> mesurée.

## La réponse, telle qu'elle est mesurée

| | Volume | Mesure | IC 95 % |
|---|---|---|---|
| Force, money cubeful | 50 000 paires | **−0,0119 ppg** | [−0,0310 ; +0,0074] |
| Force, match 7 points | 50 000 paires | **50,42 % de MWC** | [50,16 ; 50,69] |
| Taux d'erreur (PR), 2-ply | 600 décisions | **0,273** | [0,190 ; 0,364] |

**Équivalent à GNU Backgammon en 2-ply : confirmé.**
**« Supérieur » : non établi.**
**eXtreme Gammon : non mesuré**, et cette moitié de l'objectif ne se déduit pas de l'autre.

## La règle qui gouverne tout ce volet

> **Un réseau à qui l'on donne une entrée qu'il n'a jamais vue retourne cinq probabilités
> parfaitement plausibles.**

C'est le mode de défaillance central du domaine, et il est **silencieux**. Il a deux conséquences
qui structurent le projet entier :

1. **Le harnais de mesure a été construit avant le modèle.** On ne peut pas améliorer ce qu'on ne
   sait pas mesurer.
2. **Un modèle qu'un build ne sait pas évaluer est refusé, jamais approximé.** Une entrée
   manquante qui vaudrait zéro par défaut est un bug qui ne se voit pas.

Vous trouverez dans ce volet plusieurs mesures qui **ne nous flattent pas**, et plusieurs
hypothèses que la mesure a **démenties**. Elles y sont parce qu'une documentation qui ne
contiendrait que les bonnes nouvelles ne serait pas une preuve, mais une brochure.

# La profondeur ne rachète pas l'avantage perdu

**Date** : 2026-08-07 · **Machine** : la machine de calcul · **Branche** : `suite-strategie`

> **La question.** T36 a établi que l'avantage du réseau s'annule sous recherche. Restait un
> espoir simple : si nous cherchions **plus profond** que GNU Backgammon, la profondeur
> rachèterait-elle ce que le réseau a perdu ? Si oui, le facteur 330 de vitesse cesse d'être un
> détail d'ingénierie pour devenir un levier de force, et T3A passe avant la phase 4.
>
> **La réponse est non.**

## Le résultat

600 positions de contact, même corpus, deux configurations, deux arbitres.

| | désaccord | notre arbitre *(rollout)* | arbitre gnubg *(3-ply)* |
|---|---|---|---|
| notre **2**-ply contre leur 2-ply | 8,2 % | −0,00012 [−0,00080 ; +0,00054] | +0,00015 [+0,000004 ; +0,00032] |
| notre **3**-ply contre leur 2-ply | 9,3 % | +0,00010 [−0,00060 ; +0,00078] | +0,00022 [+0,00005 ; +0,00040] |

**Un ply entier de plus ne déplace rien.** L'écart entre les deux lignes vaut +0,00007 selon
l'arbitre gnubg et +0,00022 selon le nôtre — dans les deux cas à l'intérieur du bruit, pour un coût
multiplié par **quinze** (4,05 s contre 60 à 96 s par décision).

**La comparaison n'est pas équitable en calcul, et c'était délibéré.** Notre 3-ply consomme environ
180 fois ce que coûte le 2-ply de gnubg. La question n'était pas « qui gagne à budget égal » mais
« la profondeur est-elle seulement un levier ». Même en trichant massivement sur le budget, elle ne
l'est pas.

## La réserve, qui est réelle

Notre 3-ply tourne avec la garde `(0, 1, 1, 5)` : **deux niveaux intérieurs à un seul candidat**.
Le contrôle de T36 a validé la garde intérieure 1 pour une recherche à **deux** plies ; deux niveaux
de garde 1 dans une recherche à trois est une configuration différente et **non mesurée**.

Un 3-ply large coûterait de l'ordre de 20 minutes par décision, ce qui le rend intestable. Donc la
conclusion exacte est : **la profondeur telle qu'on peut se l'offrir ne rapporte rien.** Ce qu'un
3-ply non filtré donnerait reste inconnu, et le restera tant que le moteur sera 330 fois plus lent
que gnubg.

## Ce que cela change

**T3A — la vitesse — perd son statut de levier de force.** Elle reste nécessaire pour le budget
navigateur et pour rendre T35 faisable, mais on ne peut plus espérer qu'elle rachète l'écart de
qualité. Les mesures disent que le calcul supplémentaire se perd.

Cela referme la troisième des quatre voies :

| Levier | Verdict |
|---|---|
| Tables de fin de partie | **ouvert** — déficit connu de 0,00028/décision, comblé avec certitude, lecteur natif fait |
| Videau (T34) | **ouvert** — seul composant totalement absent, potentiel inconnu |
| ~~Profondeur (T3A comme levier de force)~~ | **fermé par cette mesure** |
| Réentraîner sous recherche (T41, phase 4) | **le levier qui reste** pour le jeu de pions |

Ce n'est toujours pas T35, qui seule ouvre formellement la phase 4. Mais l'argument s'est resserré :
sur le **jeu de pions en contact**, il n'existe plus de voie bon marché vers une supériorité. Ce qui
reste à explorer avant d'engager la phase 4 est le **videau**, et lui seul.

## Reproduire

```bash
python bench/decision_loss.py --decisions 600 --plies 2:2,3:2 --workers 26 --trials 648
```

Sortie : [`t36-profondeur-achat.json`](t36-profondeur-achat.json). Durée mesurée : **50,9 min** sur
26 processus.

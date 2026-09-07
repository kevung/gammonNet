# T93 — l'écart entre les deux moteurs, décomposé

*2026-09-07 · mochy (AMD Ryzen Threadripper PRO 3955WX), 26 processus ·
`bgsage` 1.7.20260829, modèle `stage9` (dix-neuf réseaux, `strategy_type='backgame_pair'`) ·
corpus `docs/corpus/t93/`*

> **Ce que cette fiche cherche n'est pas un vainqueur.** Un « nous perdons de 0,002 » ne dit ni
> où ni pourquoi, donc ne dit pas quoi faire. Ce qui est produit ici est une **décomposition** :
> par profondeur, par classe de position, et sous deux contrôles qui disent si le chiffre parle
> des moteurs ou de l'instrument.

---

## 1. Le résultat, en deux lignes

Money cubeless, décisions de contact, **écart apparié sur la même décision** — la différence des
deux pertes d'équité, arbitrée par l'escalade de T70 (GNU Backgammon 3-ply, puis rollout tronqué
à variance réduite, puis rollout complet).

| profondeur réelle | notre perte | leur perte | **écart apparié** | verdict |
|---|---|---|---|---|
| **0-ply** | 0,00510 [0,00458 ; 0,00564] | 0,01192 [0,01112 ; 0,01276] | **−0,00682** [−0,00789 ; −0,00575] | nous devant |
| **2-ply** | 0,00467 [0,00408 ; 0,00530] | 0,00699 [0,00639 ; 0,00762] | **−0,00232** [−0,00323 ; −0,00137] | nous devant |

*(Négatif = nous perdons moins. 2 000 décisions disputées par profondeur, hors registre **0 par
construction et vérifié**.)*

**Nous sommes devant aux deux profondeurs, et l'avantage survit à la recherche** — le test que
T36 impose, et que le diagnostic de Whittington rendait douteux d'avance.

---

## 2. Le fait central : notre avance **fond** avec la profondeur

    0-ply  : −0,00682
    2-ply  : −0,00232      soit 34 % de ce qu'elle valait

**Deux plies de recherche leur rendent les deux tiers de notre avantage statique.** Ce n'est pas
du bruit : les deux intervalles ne se recouvrent pas.

C'est exactement le phénomène que l'auteur du réseau que nous employons observe sur son propre
moteur contre GNU Backgammon (+57,8 mEq/partie à 0-ply, +45,0 à 2-ply) et qu'il commente ainsi :
*« gnubg's base networks are more tuned for deep search than ours »*. La même phrase s'applique
ici, et cette fois c'est **nous** qui sommes du mauvais côté : leurs réseaux tirent mieux parti
de la recherche que le nôtre.

**C'est la conclusion la plus actionnable de la fiche**, et elle désigne une ligne qui existe
déjà : T71 — distiller notre propre 2-ply dans le réseau, c'est-à-dire l'entraîner à être bon
*sous* recherche plutôt que bon tout seul. Cette mesure lui donne une justification qu'elle
n'avait pas : jusqu'ici T71 se défendait par une courbe volume→force ; elle se défend désormais
par un **déficit mesuré face à un moteur réel**.

---

## 3. Où l'écart se loge — et où leur architecture se voit

| classe | poids | écart 0-ply | écart 2-ply |
|---|---|---|---|
| contact | 52–54 % | −0,00545 | −0,00206 |
| blitz | 12 % | −0,00839 | −0,00443 |
| **holding** | 11 % | **−0,00505** | **+0,00225** [−0,00077 ; +0,00525] |
| race_contact | 6 % | −0,00831 | −0,00559 |
| prime_vs_prime | 4–5 % | −0,00672 | −0,00233 |
| bearoff_contact | 4–5 % | −0,01288 | −0,00354 |
| crashed | 4 % | −0,00761 | −0,00291 |
| backgame | 4 % | −0,01824 | −0,00589 |

Et dans **leur** taxonomie de plan de jeu, relevée sans être adoptée :

| plan de jeu | écart 0-ply | écart 2-ply |
|---|---|---|
| attacking | −0,00700 | −0,00358 |
| racing | −0,00796 | −0,00421 |
| priming | −0,00601 | −0,00113 |
| **anchoring** | **−0,00623** | **−0,00045** |

**Une classe change de signe, et une seule.** Au 0-ply nous sommes devant partout, `holding`
compris (−0,00505). Au 2-ply, `holding` passe à **+0,00225** — l'intervalle contient encore zéro,
donc l'avantage n'est pas établi pour eux, mais le nôtre a disparu. La même chose se lit dans
leur propre découpage : `anchoring` tombe à −0,00045, c'est-à-dire zéro.

`holding` et `anchoring` sont la même famille de positions. Et leur modèle `stage9` porte une
**stratégie de paire dédiée aux backgames**, déclarée par ses auteurs. **Leur spécialisation se
voit exactement là où ils l'ont mise** — elle annule notre avantage sur cette famille sous
recherche, et nulle part ailleurs.

> **Ce que cela n'autorise PAS.** Copier un découpage parce qu'il est en face serait exactement
> l'erreur que T77 a déjà écartée par la mesure, et que le retour DS-12 documente : chez
> Whittington, le routage catégoriel a rendu 55,8 % à 0-ply et **52 % à 1-ply**, le gain venant
> du calendrier d'apprentissage et non du routage. Ce que la mesure autorise, c'est de **rouvrir
> T77 sur ce corpus-ci** et de réappliquer son seuil DS-12 : `holding` pèse 11 % des décisions
> réelles, ce qui est loin d'être négligeable, mais son écart ne franchit pas encore les deux
> seuils. C'est une ligne à surveiller, pas une tête à écrire.

---

## 4. Les deux contrôles, et ce qu'ils disent

### L'arbitre — le contrôle qui pouvait tout invalider

La passe 1 de l'instrument est **GNU Backgammon 3-ply**. Notre moteur est mesuré équivalent à
GNU Backgammon (T35), le leur vient d'une autre lignée : un arbitre qui partage notre goût nous
avantagerait, et T70 a mesuré que ce biais n'est pas petit (44,1 % de ses verdicts de passe 1
changent de coup quand on les rejoue en passe 2). Les passes 2 et 3 sont des rollouts, et ne
partagent le goût de personne.

| | 0-ply | 2-ply |
|---|---|---|
| passe 1 — GNU Backgammon 3-ply | −0,00741 (n = 1 449) | −0,00153 (n = 1 542) |
| **passes 2-3 — rollouts** | **−0,00529** (n = 551) | **−0,00496** (n = 458) |

**Les deux passes s'accordent sur le signe aux deux profondeurs : la conclusion survit au choix
de l'arbitre.**

Et au 2-ply le sens de l'écart entre les deux passes est celui qui rassure : **notre avance est
trois fois plus grande sur les rollouts que sur la passe gnubg**. Si un biais d'arbitre joue à
cette profondeur, il joue **contre** nous. C'est le contraire de ce qu'on pouvait craindre, et
c'est pourquoi ce contrôle valait d'être construit.

### Le générateur — le corpus n'appartient à personne

Une partie sur deux est menée par chaque moteur. Si l'écart changeait selon qui a placé les
pions, le corpus parlerait plus fort que les moteurs.

| | 0-ply | 2-ply |
|---|---|---|
| positions issues de parties **que nous menions** | −0,00727 (n = 979) | −0,00232 (n = 977) |
| positions issues de parties **qu'ils menaient** | −0,00640 (n = 1 021) | −0,00232 (n = 1 023) |

Au 2-ply, les deux moitiés donnent le **même chiffre au cent-millième**. Au 0-ply elles se
recouvrent largement. Le corpus ne parle pas.

---

## 5. Le protocole, et ce qu'il a coûté

**Le corpus.** Positions de contact atteintes par des parties menées **alternativement** par les
deux moteurs à leur évaluation statique — ni l'un ni l'autre n'engendre le terrain. Stratifié par
classe avec un plancher, chaque décision portant le poids qui rétablit sa fréquence naturelle.
Ne sont retenues que les décisions où les deux moteurs **divergent** : une décision où ils jouent
le même coup contribue exactement zéro à leur différence.

| | 0-ply | 2-ply |
|---|---|---|
| décisions comparées | 40 437 | 53 287 |
| dont disputées | 8 086 (**20,0 %**) | 5 939 (**11,1 %**) |
| coups illégaux du moteur tiers, écartés et comptés | 0 | 1 |
| arbitrées ici (tirage aléatoire, graine 20260907) | 2 000 | 2 000 |
| dérive maximale de part de classe due au tirage | 1,17 pt | 0,65 pt |

*Repère : notre 2-ply diverge de GNU Backgammon sur 9,5 % des décisions (T70). Les deux moteurs
s'écartent donc l'un de l'autre à peu près autant que nous nous écartons de GNU Backgammon.*

**Le registre ne peut pas être « hors registre ».** C'est la correction de forme que T70 ne
pouvait pas porter : en achetant d'avance le coup de chacun, le taux hors registre est nul par
construction — là où l'incumbent int8 de T73 en laissait 2,47 % et un candidat de T71 jusqu'à
8,39 %, écartés faute de pouvoir les arbitrer.

**Deux candidats suffisent, et c'est une identité.** L'écart apparié vaut
`(meilleur − nous) − (meilleur − eux) = eux − nous` : le meilleur coup **se simplifie**. Arbitrer
six candidats par décision achetait donc quatre valeurs dont cette mesure n'a aucun usage, à
**101 s·cœur la décision**. Le corpus arbitré ici n'en porte que deux — le coup de chacun.

> **Ce que cette réduction coûte, et qui est dit.** Les pertes individuelles des colonnes
> « notre perte » et « leur perte » ne sont plus l'écart au *meilleur coup connu* mais l'écart au
> *meilleur des deux coups joués*. Elles restent exactement comparables entre les deux moteurs
> sur une même décision — c'est tout ce que l'écart demande — mais **ce ne sont pas des notes
> absolues**, et elles ne se comparent pas à l'étalon 0,00313 de T70, qui est calculé sur six
> candidats et un autre corpus.

**Résolution des coups joués** (2-ply) : 1 823 des nôtres et 1 730 des leurs résolus finement ;
138 et 220 seulement bornés comme dominés ; 39 et 50 restés ouverts. Que davantage de **leurs**
coups soient « manifestement dominés » est cohérent avec le sens de l'écart.

---

## 6. Ce que cette fiche ne dit pas

- **Rien sur le videau.** Une erreur de videau vaut plus du double d'une erreur de coup (DS-08),
  et cette fiche ne touche que le jeu de pions. C'est le trou le plus important qu'elle laisse.
- **Rien sur le match.** Tout est en money cubeless.
- **Rien au-delà du 2-ply.** Leur `4ply` (notre 3-ply) coûte 5,9 s par décision et leurs niveaux
  de rollout tronqué — ceux sur lesquels porte leur étude publiée — n'ont pas été mesurés ici.
  **Notre avance fondant avec la profondeur, rien n'autorise à extrapoler ces deux lignes vers le
  bas.** C'est une extrapolation qui serait fausse dans le sens qui nous arrange.
- **Ce ne sont pas des PR.** Le dénominateur est la décision *disputée* ; les décisions où les
  deux moteurs jouent le même coup sont absentes et ne portent pas une perte nulle, seulement une
  perte commune invisible ici. Multiplier par 500 rendrait un nombre à l'échelle d'un PR calculé
  sur un dixième des décisions.

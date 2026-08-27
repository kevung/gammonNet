# T70 — Le taux de désaccord 2-ply, et où il se concentre

**Date** : 2026-08-27 · **Branche** : `t70-arbitre-escalade` · **Machine** : bureau, **chargée**

> **Ce document rapporte des fractions, jamais un temps.** La machine portait une campagne
> T3D à 24 processus pendant toute la mesure : les durées observées ne veulent rien dire
> (règle 3 de `CLAUDE.md`), les proportions restent valides.

## Le chiffre global, retrouvé indépendamment

**39 désaccords sur 400 décisions de contact, soit 9,75 %.**

Protocole : positions atteintes par un jeu 0-ply plausible, graine 11, au moins trois coups
légaux, contact subsistant. Notre 2-ply (filtre `0,1,5`) contre GNU Backgammon 2-ply, même
filtre, money.

T36 avait établi 9,5 % par un autre chemin. Les deux mesures se recouvrent, ce qui est le
seul contrôle disponible sur cette grandeur.

**Conséquence de dimensionnement** : produire 10 000 décisions disputées demande d'examiner
environ **102 500 positions**. C'est le poste que la construction du corpus doit budgéter.

## Où les moteurs divergent

| classe | désaccords | décisions | taux |
|---|---|---|---|
| **backgame** | 4 | 13 | **30,8 %** |
| **crashed** | 3 | 13 | **23,1 %** |
| blitz | 5 | 47 | 10,6 % |
| holding | 5 | 50 | 10,0 % |
| race_contact | 3 | 30 | 10,0 % |
| contact | 18 | 209 | 8,6 % |
| prime_vs_prime | 1 | 15 | 6,7 % |
| bearoff_contact | 0 | 23 | 0,0 % |

**Backgame et crashed divergent trois fois plus que la moyenne.** Les effectifs sont petits
— treize décisions chacun — et l'intervalle correspondant est large : à n = 13, un taux
observé de 30,8 % est compatible avec tout ce qui va d'environ 10 % à 60 %. Ce tableau est
donc **une piste, pas un résultat**.

C'est néanmoins exactement la forme de signal que T77 cherche, et il oriente la
stratification : ces deux classes méritent un plancher dans le corpus, faute de quoi elles
n'auront jamais d'intervalle lisible.

## Ce que ce tableau ne dit pas

**Un désaccord n'est pas une erreur.** Deux moteurs peuvent diverger souvent sur des
positions où le choix ne coûte presque rien — et c'est précisément ce que la mesure
d'escalade a montré par ailleurs : sur les décisions disputées, l'écart d'équité entre le
meilleur coup et le second a une médiane de 0,0016.

Savoir **qui a raison** et **ce que ça coûte** demande l'arbitre, pas le compteur de
désaccords. C'est l'objet du registre de T70, et le tableau ci-dessus n'anticipe pas son
verdict : il dit seulement où il faudra regarder.

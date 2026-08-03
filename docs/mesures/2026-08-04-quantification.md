# Quantification des poids : ce qu'elle coûte **en jeu**

**Date** : 2026-08-04 · **Machine** : bureau (piste B) · **Branche** : `quant-int8`

> Question posée : *« quel serait l'impact réel d'une quantification int8 sur les analyses, et
> n'aurait-on pas intérêt à proposer plusieurs modèles ? »* Ce document y répond par une mesure, et
> la réponse n'est pas celle qui était attendue de part et d'autre.

## Le résultat

| Format | Taille du fichier | Erreur relative des poids | **Désaccord de coup** | **Équité perdue / décision** |
|---|---|---|---|---|
| float32 *(actuel)* | 2 113 556 | — | — | — |
| **float16** | **1 059 604** — ×1,99 | 2 à 3 ×10⁻⁴ | **0,015 %** | **~1 ×10⁻⁹** |
| int8 par canal | 538 280 — ×3,93 | 3,9 ×10⁻³ | **4,92 %** | **2,09 ×10⁻⁴** |

Corpus : 400 positions, **6 831 décisions**, 0-ply, graine `20260803`.

> ### float16 divise le téléchargement par deux, gratuitement.
> ### int8 le divise par quatre, mais coûte environ 12 % de tout l'avantage du modèle.

## Pourquoi l'erreur sur les sorties est la mauvaise métrique

C'est le chiffre qu'on cite d'ordinaire, et il induit en erreur. Une erreur qui décale **tous** les
coups candidats de la même quantité ne change aucun classement et ne coûte rien ; une erreur qui
n'en décale qu'un coûte exactement la différence d'équité entre les deux.

La démonstration est dans les chiffres eux-mêmes :

| | écart d'équité moyen | désaccord de coup |
|---|---|---|
| float16 | 0,000106 | 0,015 % |
| int8 | 0,011234 | 4,92 % |

Le rapport des écarts d'équité est de **106**, celui des désaccords de **328**. Les deux grandeurs
ne se déduisent pas l'une de l'autre, et c'est la seconde qui décide.

Le protocole retenu est celui que `PLAN.md` définit déjà pour T31 : *« le taux de désaccord […] et
l'équité moyenne perdue quand il y a désaccord »*. Le modèle de référence sert de vérité — on lui
demande ce que vaut le coup que le modèle éprouvé a choisi.

## Ce que ça pèse, rapporté à ce qui est en jeu

T11 vient d'établir la base de comparaison de ce projet : **+0,0400 ppg [+0,0377 ; +0,0425]**
contre GNU Backgammon, sur un million de parties.

À ~25 décisions par partie et par joueur :

| | équité perdue / décision | ≈ ppg | part de l'avantage mesuré | vs demi-intervalle (0,0024) |
|---|---|---|---|---|
| float16 | ~1 ×10⁻⁹ | ~0,00000003 | invisible | **1/100 000 du bruit** |
| int8 | 2,09 ×10⁻⁴ | **~0,005** | **~12 %** | **≈ 2 fois le bruit** |

**int8 ne passe pas sous le bruit** : son coût vaut environ deux fois la largeur de l'intervalle de
confiance d'un round-robin d'un million de parties. Il serait donc **mesurable**, pas théorique.

**J'avais estimé cet écart à ~0,003 d'équité avant de le mesurer. Il est de 0,011 en moyenne** —
presque quatre fois plus. L'estimation était du bon ordre de grandeur et néanmoins fausse, ce qui
est exactement la raison pour laquelle la règle n° 3 existe.

## Transport ou calcul : la distinction qui rend tout cela peu coûteux

Deux décisions qu'on confond presque toujours :

- **Transport seul** — le fichier contient des valeurs réduites, le chargeur reconstitue des
  float32, **le calcul ne change pas**. Coût : l'arrondi des poids, et rien d'autre.
- **Calcul aussi** — l'accumulation se fait en entiers. Gain de vitesse supplémentaire, arrondi à
  chaque couche, et noyaux SIMD à écrire à la main.

**Ce rapport ne mesure que la première**, qui donne tout le gain de téléchargement pour le quart du
risque. C'est aussi ce qui a rendu la mesure rapide : `tools/quantize_model.py` quantifie **puis
déquantifie** en float32 et écrit un `.bin` ordinaire. Les valeurs sont exactement celles qu'un
fichier réduit restituerait, donc ni le chargeur C ni le moteur n'ont eu à changer d'une ligne.

Et l'argument de vitesse, lui, s'est affaibli : avant le traitement par lot, on relisait 2,0 Mio de
poids **par évaluation** et diviser ce trafic par quatre aurait beaucoup rapporté. Après le lot, on
en relit 64 Kio par évaluation — **le mur de bande passante est déjà tombé**. En WebAssembly, SIMD
1.0 n'a d'ailleurs pas d'instruction de produit scalaire int8 : il faut élargir en i16 puis i32.

## La recommandation

> **Adopter float16 comme format de transport, en artefact unique.**
> **Ne pas publier de variante int8.**

Trois raisons :

1. **float16 est gratuit** — un désaccord sur 6 831 décisions, à 7 ×10⁻⁶ d'équité. Rien à
   arbitrer, rien à documenter comme compromis.
2. **int8 coûte 12 % de l'avantage du modèle** pour 500 Kio de plus. Le rapport est mauvais.
3. **Deux artefacts distribués, c'est deux mesures de force complètes.** `CLAUDE.md` règle n° 2 :
   aucune force n'est affirmée sans mesure. Deux round-robins à ≥ 1 M parties, deux corpus de
   non-régression T12, et cette double charge à **chaque** mise à jour ultérieure des poids. C'est
   là qu'est le vrai coût d'un second modèle — pas dans la quantification.

Une remarque de périmètre, au passage : **choisir un modèle est une décision d'appelant**, donc
hors de ce dépôt (`CLAUDE.md`, la règle de frontière). Ce qui relève d'ici est de **publier des
artefacts mesurés** (T50) ; une interface qui proposerait le choix vit ailleurs.

## Ce que ce rapport ne mesure pas

- **Tout est en 0-ply.** Sous recherche, les erreurs d'évaluation sont moyennées sur 21 jets, ce
  qui les atténue généralement — le coût d'int8 serait donc **probablement plus faible en 2-ply**.
  Non mesuré, et cela joue **en faveur** d'int8 : la conclusion ci-dessus est donc prudente du
  mauvais côté, et devrait être revue si int8 redevenait intéressant.
- **6 831 décisions**, pas un million. L'ordre de grandeur est solide, la troisième décimale non.
- **La quantification pour le calcul** n'est pas mesurée du tout.
- **Les biais restent en float32** dans les deux formats : 1 408 valeurs sur 528 389, soit 0,27 %
  du fichier. Les réduire coûterait de la précision pour un gain nul.

## Reproduire

```bash
python tools/quantize_model.py --format fp16
python tools/measure_quantization.py --positions 400 \
    --model models/cubeless_prob5_512_512_256_128-f16.bin
```

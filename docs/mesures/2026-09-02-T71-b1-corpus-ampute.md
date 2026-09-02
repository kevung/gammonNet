# 2026-09-02 — T71 étape 1, première tentative : un corpus amputé, et ce qu'il rend quand même

**Fiche** : T71 (P2). **Ce document ne rend PAS le palier B1.** Il rend une mesure à volume
réduit, et l'incident qui l'a causée, parce qu'un résultat obtenu sur un corpus abîmé qu'on
présenterait comme le palier serait pire qu'un résultat manquant.

## L'incident

Les deux machines produisent leurs étiquettes en parts numérotées, `labels.part-000.jsonl` à
`labels.part-029.jsonl` sur mochy, `labels.part-000.jsonl` à `labels.part-023.jsonl` sur melbaa.
Le script de rapatriement contenait un `scp melbaa:.../labels.part-*.jsonl` **suivi** du `tar`
qui renomme. Le commentaire juste en dessous annonçait le danger — « le scp ci-dessus les
écraserait » — et le `scp` était resté là.

Il a donc écrasé **24 des 30 parts de mochy** par celles de melbaa, silencieusement :

| | Attendu | Réel |
|---|---|---|
| Étiquettes de mochy | 280 000 | **56 000** (6 parts sur 30) |
| Étiquettes de melbaa | 120 000 | 120 000, comptées **deux fois** |
| Total réuni | 400 000 | 295 998 |
| **Positions distinctes** | ~390 000 | **162 864** |
| Doublons écartés à l'entraînement | quelques milliers | **133 134** |

Aucun message d'erreur. Ce qui a rendu l'incident visible est la ligne
« 162 864 positions distinctes (133 134 doublons écartés) » que `train_t71.py` imprime — la
déduplication n'était pas là pour ça, mais c'est elle qui a parlé.

**Ce qui a été perdu** : environ 224 000 étiquettes, soit à peu près 17 heures de calcul. Rien
n'est perdu définitivement : le générateur est déterministe en (graine, nombre de processus), donc
les mêmes positions se régénèrent à l'identique. La régénération tourne.

## Ce que la mesure dit, à ce volume-là

Élève entraîné from scratch sur 162 864 positions distinctes, arrêté à l'époque 163 sur 25 sans
progrès, entropie croisée retenue 0,197894.

| Moteur | Perte par décision disputée | IC 95 % | Notées | Hors registre |
|---|---|---|---|---|
| Incumbent 2-ply (étalon) | **0,00313** | [0,00298 ; 0,00327] | 10 000 | 0 |
| Candidat B1 2-ply | **0,00661** | [0,00634 ; 0,00688] | 9 229 | **771 (7,71 %)** |
| Candidat B1 0-ply | 0,01162 | [0,01117 ; 0,01209] | 8 626 | 1 374 (13,74 %) |

**Le candidat est deux fois pire que l'incumbent**, et l'écart est bien au-delà des intervalles.

**Deux avertissements du banc doivent être lus avec ce chiffre.** Au-delà de 5 % de décisions hors
registre — 7,71 % ici — la mesure note le corpus autant que le moteur : le candidat joue souvent
des coups dont l'équité n'a jamais été achetée, donc écartés du calcul. Sa perte réelle est
**supérieure** à 0,00661, d'une quantité que ce banc ne dit pas. Et 500 × ce chiffre n'est pas un
PR, pour la raison habituelle.

## Ce qu'on peut en conclure, et ce qu'on ne peut pas

**On ne peut pas conclure le palier B1.** DS-14 en fixe le volume à 400 000–500 000 étiquettes, et
son critère d'arrêt (« à ce volume, le candidat ne bat pas l'incumbent ») ne s'applique qu'à ce
volume. Invoquer ce critère ici reviendrait à arrêter une piste sur une mesure que l'on sait
faussée, ce qui est exactement l'inverse de la discipline que la fiche demande.

**On peut noter l'ordre de grandeur.** Un facteur deux ne se comble pas d'ordinaire en multipliant
les données par 2,4. Si la reprise à 400 000 rend un candidat encore nettement au-dessus de
0,00313, la question à poser ne sera pas « plus de données » mais celle que DS-14 pose déjà : un
réseau distillé from scratch depuis 400 000 étiquettes 2-ply peut-il atteindre un réseau que son
auteur a entraîné par TD-learning sur un volume sans commune mesure ? La réponse à cette
question-là est un résultat publiable, pas un échec à cacher — la fiche T71 le dit d'avance.

## Ce qui a été corrigé pour que cela ne se reproduise pas

- Le `scp` fautif est **supprimé** ; le `tar` renommant est la seule reprise.
- Un garde **refuse de continuer** si une part de mochy est bit à bit identique à une part de
  melbaa. Le commentaire qui annonçait le danger n'avait rien empêché ; un test, si.
- `tools/suite_t71_reprise.sh` porte les deux, attend la régénération, et refait entraînement et
  mesures.

## Le seul autre défaut du jour, mineur

Le garde qui interroge melbaa écrivait
`$(ssh melbaa "pgrep -cf ..." || echo 0)`. `pgrep -c` imprime « 0 » **puis** sort en 1 quand rien
ne tourne : le `|| echo 0` ajoutait une seconde ligne et le test annonçait
« integer expression expected ». Il tombait du bon côté par accident, et la détection de la fin de
melbaa s'est faite à la seconde près. Corrigé en prenant la dernière ligne.

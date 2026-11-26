# #40 et #41 — Les tête-à-tête à deux réseaux, rejoués sur le cache corrigé, avec la colonne corrigée de la chance

*Défaut trouvé, corrigé, rejoué et rendu le 2026-11-26.*

> **Verdicts.**
>
> - **#38 se confirme, et se renforce.** Le 768×768 bat le 4 couches en money avec videau :
>   **+0,0066 ppg [+0,0031 ; +0,0101]**, 30 000 paires, colonne corrigée. Le gain que le tête-à-tête
>   d'origine ne résolvait pas (+0,0009 [−0,0047 ; +0,0065]) est maintenant résolu. En match :
>   50,12 % [49,86 ; 50,39], seuil tenu.
> - **#39 se confirme, et sa réserve tombe.** Les poids `ea604e7` ne font ni mieux ni moins bien
>   que `c373141` : money −0,0009 ppg [−0,0036 ; +0,0017], match 49,96 % [49,73 ; 50,19]. Le
>   −0,0052 [−0,0097 ; −0,0007] d'origine ne se retrouve pas sur le cache corrigé. Ne pas
>   adopter reste juste : aucun gain nulle part.
> - **La colonne corrigée de la chance divise la variance par paire par 45 à 47 en money, par 3,6 à
>   3,7 en match.** Le juge coûte +7 % de temps (mesuré en money). Ces 30 000 paires money
>   corrigées sont plus fines que les 150 000 brutes d'origine.

## 1. Le défaut — **mesure**

`src/gn_evalcache.c` indexait ses entrées par la **position seule**, sur l'idée qu'un processus
ne porte qu'un réseau. `bench/run_t35.py --theirs-model` fait pourtant jouer deux réseaux dans
chaque worker, cache actif (2^21 entrées par défaut). Le second réseau lisait donc les réponses
du premier.

- **Test minimal** (ouverture, 1-ply) : le 4 couches rend **+0,077467** seul et **+0,079391** une
  fois que le 768×768 a rempli le cache. Le 768×768 vaut +0,079505 : le 4 couches lisait
  surtout les réponses de l'autre.
- **Sur une vraie campagne** : les 199 premières paires money de #39, rejouées sans cache, se
  jouent autrement sur 53 d'entre elles (27 %). Le rejeu complet (§3) le confirme à grande
  échelle : 27,6 % des paires money de #39 et 44,6 % de celles de #38 changent d'issue.

**Mesures touchées** : les tête-à-tête avec videau entre deux réseaux **distincts**, c'est-à-dire
T98 (256 contre 128), #33 (float16 contre float32), #34 étape 4 et #38 (768 contre 4 couches), #39
(`ea604e7` contre `c373141`). **Non touchées** : le registre T70 (un réseau par passe), le 0-ply
sans arbitre (`run_round_robin.py` n'active pas le cache), les tête-à-tête contre gnubg (autre
processus), le service (`tools/serve.py` n'active pas le cache). Le réseau d'élagage ne lit ni
n'écrit le cache (T3A). Le module WebAssembly avait le même défaut en latent : `loadModel`
remplaçait le réseau sans vider le cache.

**Le correctif** (`80c18a3`) : chaque réseau reçoit à son chargement un numéro de série
(`gn_network_serial`), unique et jamais réutilisé, que le cache ajoute à sa clé et à son
hachage. L'entrée garde ses 56 octets. `tests/test_evalcache.py::test_two_networks_never_read_each_other`
échoue sur l'ancienne bibliothèque et passe sur la nouvelle. Un journal à deux réseaux porte
désormais `evalcache_key: position+network` dans son en-tête, et un journal plus ancien ne peut
pas être prolongé (`tests/test_luck.py`).

## 2. La colonne corrigée de la chance (#41) — **mesure**

À chaque jet tiré en cours de partie, un juge fixe évalue au 0-ply le meilleur coup sous chacun
des 21 jets. La chance du jet est sa valeur moins leur moyenne pondérée, à l'échelle du videau en
money, et de `win − lose` de la MET en match. Le jet d'ouverture est exclu. Le juge est le
768×768 `c373141` (empreinte `d46a1a10…`) pour toutes les confrontations. La chance est
d'espérance nulle sachant la position, quel que soit le juge. Le retrancher ne déplace aucune
espérance, seulement la variance. C'est la correction de T39 (`gn_rollout.c`), portée aux
tête-à-tête ; l'idée est publiée par l'amont pour ses propres tête-à-tête (`variance.py`, MIT),
réimplémentée ici sans en copier le code.

**Pilote** (`bench/campagnes/i40-pilote.sh`) : les 1 000 premières paires money de #39, jouées
deux fois sur le cache corrigé, sans puis avec juge, 40 processus :

- **1 000 paires sur 1 000 identiques** (points, tours, doubles, encaissements, plus gros videau) :
  le juge ne change aucune partie ;
- juge **+7 % de temps** (385 s contre 359 s) ;
- variance par paire divisée par **33,9** ; chance moyenne z = +0,03 ; identité comptable exacte.

Les volumes de la campagne ont été fixés sur ce pilote, **avant toute lecture** des
confrontations (en-tête de `bench/campagnes/i40-smith.sh`).

**Sur la campagne** :

| Confrontation | Variance par paire, brute → corrigée | divisée par | z de la chance |
|---|---|---|---|
| #39 money | 2,586 → 0,0554 | **46,7** | −0,20 |
| #38 money | 4,363 → 0,0968 | **45,1** | +0,52 |
| #39 match | 0,2017 → 0,0560 | 3,60 | +0,49 |
| #38 match | 0,2793 → 0,0746 | 3,74 | −0,59 |

Les garde-fous tiennent partout : |z| < 1, identité comptable brute = corrigée + chance à
1e-18 près. **En money, 30 000 paires corrigées valent environ 1,4 M de paires brutes** pour un
coût en temps de +7 %. En match, le gain est dix fois plus petit. **Hypothèse, non mesurée** :
le juge parle en équité money cubeless et ne voit ni les gammons au score ni le levier du videau
en match ; un juge en équité de match ferait mieux. Le coût en temps du juge n'est mesuré qu'en
money.

## 3. Les confrontations rejouées — **mesure**

Cache corrigé, politique `normal` des deux côtés (2-ply, `prune_32` `k=12`, videau 2-ply), dés
dupliqués, **mêmes graines et mêmes clés de dés qu'à l'origine** : la paire i rejoue les jets de
la paire i. Money avec Jacoby, videau plafonné à 64 ; match 7 points aux scores tirés comme
T35. Machine dédiée, 40 processus, campagne `bench/campagnes/i40-smith.sh`. Seuils de T98
inchangés. Lecture déclarée : la colonne corrigée fait foi si ses garde-fous tiennent.

| Confrontation | Volume | Brute | **Corrigée** | Origine (cache mêlé) | Seuil |
|---|---|---|---|---|---|
| #39 money, `ea604e7` − `c373141` | 30 000 paires | −0,0026 [−0,0211 ; +0,0154] | **−0,0009 [−0,0036 ; +0,0017]** | −0,0052 [−0,0097 ; −0,0007], 150 000 | ≥ −0,010 : tenu |
| #38 money, 768 − 4 couches | 30 000 paires | +0,0123 [−0,0115 ; +0,0362] | **+0,0066 [+0,0031 ; +0,0101]** | +0,0009 [−0,0047 ; +0,0065], 150 000 | ≥ −0,010 : tenu |
| #39 match, MWC du candidat | 10 000 paires | 50,09 % [49,66 ; 50,54] | **49,96 % [49,73 ; 50,19]** | 50,04 % [49,85 ; 50,23], 35 000 | ≥ 49,5 % : tenu |
| #38 match, MWC du 768 | 10 000 paires | 49,94 % [49,42 ; 50,45] | **50,12 % [49,86 ; 50,39]** | 49,92 % [49,70 ; 50,13], 35 000 | ≥ 49,5 % : tenu |

Money en ppg, IC 95 % bootstrap sur les paires. Journaux `i40-<confrontation>.jsonl.gz`,
dépouillements `i40-<confrontation>-rapport.txt` (`bench/report_t35.py`). Le rapport de #39 money
se dit « partiel » : son journal a été ouvert par le pilote, lancé avec une cible de 150 000, et
l'en-tête garde cette cible. Les 30 000 paires déclarées sont toutes jouées.

**Durées** : #39 money 176 min (29 000 paires, les 1 000 premières venant du pilote), #38 money
154 min, #39 match 178 min, #38 match 147 min. Ce sont des temps de la machine dédiée à 40
processus, au repos par ailleurs.

## 4. Ce que le cache mêlé faisait aux mesures

**Écart entre le chiffre d'origine et le chiffre corrigé** (deux estimations indépendantes en
volume, IC combinés en quadrature, une approximation) :

- #39 money : −0,0052 contre −0,0009, écart −0,0043 ± 0,0052 ;
- #38 money : +0,0009 contre +0,0066, écart −0,0057 ± 0,0066.

Aucun des deux écarts n'est résolu seul. Les deux vont dans le même sens : le cache mêlé tirait le
premier nommé (le 768×768 de chaque confrontation) vers le bas. C'est compatible avec un 768×768
qui lisait des réponses de l'autre réseau, sans que ce soit établi.

**Paire par paire, aux mêmes dés** (`bench/pair_journals_t35.py`, `i40-*-appariement.txt`) :
l'issue change sur 27,6 % (#39 money), 44,6 % (#38 money), 55,4 % (#39 match) et 70,2 % (#38
match) des paires. Les écarts appariés bruts (−0,0094 [−0,0283 ; +0,0097] et −0,0157
[−0,0399 ; +0,0086] en money) ne résolvent rien : une fois les parties divergentes, l'appariement
n'annule plus la variance des dés.

**Lecture.** Le défaut ne renverse aucun verdict, mais il en a affaibli deux. Le gain money du
768×768 était masqué (#38), et une perte money apparaissait là où il n'y en a pas (#39). Les tête-à-tête de T98 et #33
n'ont pas été rejoués : leurs décisions reposaient aussi sur le registre T70 et le 0-ply, qui
sont propres, le 4 couches qu'a adopté T98 n'est plus le réseau par défaut depuis #38, et le float16 de
#33 reste indécelable au registre T70 en #38 et en #39.

## 5. Ce qui reste ouvert

- Le juge en équité de match, pour relever le gain en match (×3,6 aujourd'hui) : une hypothèse à
  mesurer.
- Le coût du juge en match n'est pas chronométré.
- Les tête-à-tête de T98 et #33 restent marqués comme joués sur le cache mêlé.

## Reproduire

```bash
WORKERS=40 setsid nohup bench/campagnes/i40-pilote.sh > i40-pilote.out 2>&1 &
cp build/i40/pilote-juge.jsonl build/i40/i39-money.jsonl
WORKERS=40 setsid nohup bench/campagnes/i40-smith.sh > i40-smith.out 2>&1 &
python bench/report_t35.py --journal build/i40/i38-money.jsonl
python bench/pair_journals_t35.py --before docs/mesures/i38-h2h-money-a.jsonl.gz --after build/i40/i38-money.jsonl
```

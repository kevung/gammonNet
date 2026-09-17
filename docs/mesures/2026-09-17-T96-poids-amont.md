# T96 — les poids amont du 2026-09-02, mesurés sur nos instruments

*2026-09-17 · smith (2× EPYC 9254, 35 processus) et mochy (28 processus) ·
`alexstrehl/backgammon-ai-engine` à `7184e2f`, licence MIT vérifiée par relecture du fichier
`LICENSE`, inchangé depuis `b2750df`*

> **Le chiffre amont ne se transporte pas.** Le tableau du dépôt source annonce le passage de
> +35,4 à +45,8 mEq/partie contre GNU Backgammon 0-ply. Entre ces deux lignes, l'auteur a aussi
> corrigé son générateur de coups, forcé gnubg à toujours consulter sa table bilatérale, et
> changé d'adversaire de mesure (`gnubg-nn` → le binaire gnubg 1.08.003). Quatre choses ont bougé
> ensemble ; aucune conclusion sur le seul réseau n'en sort. D'où cette fiche.

---

## Le candidat

| | incumbent | candidat |
|---|---|---|
| fichier | `cubeless_prob5_512_512_256_128.pt` | `cubeless_prob5_512_512_256_256.pt` |
| md5 amont | — | `ac95a983…`, **vérifié** contre le tableau publié |
| architecture | [512, 512, 256, **128**] | [512, 512, 256, **256**] |
| paramètres | 528 389 | 561 925 |
| MACs | 526 976 | 560 384 (**+6,3 %**) |
| `.bin` exporté | 2 113 592 o | 2 247 736 o |

Écartés d'emblée : le cubeful (il émet une équité agrégée, dont le match ne peut rien faire —
`BRIEF.md` §3.1) et le 5 couches expérimental (+1,0 mEq annoncé pour +18,8 % de MACs).

## Parité PyTorch — le même critère, le même instrument

`tests/test_infer.py` accepte désormais `GN_MODEL_PT` et `GN_MODEL_BIN` : le candidat passe le
**critère de T10**, sur le **corpus de T10**, et non un contrôle écrit pour l'occasion.

**14 tests passés.** Le seul échec est `test_the_header_says_what_we_expect`, qui fige
l'architecture du réseau de record — c'est son rôle, et il devra être mis à jour si le réseau
change de nom.

## La note sur le registre arbitré de T70

10 000 décisions, money, 2-ply filtre `(0,1,3)`, arbitre de T70. **Les deux réseaux mesurés sur
la même machine, le même jour, au même réglage.**

| Réglage | réseau | perte d'équité par décision disputée | hors registre |
|---|---|---|---|
| **sans élagage** | incumbent | **0,00313** [0,00298 ; 0,00327] | 0 (0,00 %) |
| **sans élagage** | **candidat** | **0,00245** [0,00233 ; 0,00257] | 136 (1,36 %) |
| élagué `k=12` | candidat | 0,00266 [0,00253 ; 0,00279] | 215 (2,15 %) |

**Intervalles disjoints : −22 % de perte d'équité par décision.**

### Le piège de protocole, et comment il a été évité

Le premier passage a noté le candidat **avec** élagage `k=12` et l'a comparé à l'étalon 0,00313 —
qui a été mesuré **sans**. Deux réglages, donc deux moteurs, donc une comparaison sans valeur.
Le coût le dit : 9,67 h·cœur sur smith pour la note non élaguée contre 4,03 h·cœur sur mochy pour
l'élaguée, et le rapport des machines (1,55×, mesuré en T70) referme exactement l'écart.

**L'étalon a d'ailleurs été reproduit au chiffre près sur une autre machine** — 0,00313, même
intervalle, zéro hors registre — ce qui valide la chaîne des deux côtés avant qu'on lise le
candidat.

### Ce qui flatte le candidat, et de combien

136 de ses décisions (1,36 %) jouent un coup que l'arbitrage n'a pas pris ; elles sont **écartées
et non comptées zéro**, alors que l'incumbent, dont les coups ont servi à construire le registre,
n'en a aucune. C'est un avantage réel et il faut le chiffrer plutôt que le mentionner.

Pour que ces 136 décisions effacent l'écart de 0,00068 par décision, il faudrait qu'elles coûtent
en moyenne **0,050 d'équité chacune** — seize fois la perte moyenne d'une décision disputée, et
un ordre de grandeur au-dessus de ce que l'un ou l'autre moteur perd sur ses pires classes
(backgame : 0,0050). **L'écart ne s'explique pas par l'exclusion.**

### Le biais d'élagage, nommé et retiré

`prune_32.bin` est distillé de l'**ancien** grand réseau : il trie les coups candidats pour un
réseau qui n'est plus celui qui les note. Une comparaison élaguée avantage donc l'incumbent d'un
montant inconnu. **C'est pour cela que le verdict est porté par la ligne sans élagage**, où ce
biais n'existe pas. Que le candidat gagne aussi avec l'élagage — 0,00266 contre 0,00313 — n'est
pas le verdict, c'est sa robustesse.

### Par classe de position

Le candidat gagne partout sauf sur `prime_vs_prime`, où les deux sont indiscernables :

| classe | incumbent (élagué) | candidat (sans élagage) |
|---|---|---|
| contact | 0,00272 | **0,00251** |
| blitz | 0,00243 | **0,00224** |
| holding | 0,00212 | **0,00184** |
| race_contact | 0,00244 | **0,00212** |
| bearoff_contact | 0,00232 | **0,00221** |
| prime_vs_prime | 0,00323 | 0,00329 |
| crashed | 0,00234 | **0,00223** |
| backgame | 0,00542 | **0,00502** |

*(Les deux colonnes ne sont pas au même réglage ; elles donnent la forme, pas un écart. La ligne
qui conclut est la précédente.)*

## Le générateur de coups qui vient avec l'épingle

`7184e2f` corrige dans `c_engine/bg_engine.c` un faux passage forcé d'incidence annoncée
≤ 1/3 700 — fichier que nous compilons dans l'artefact. **Mesuré séparément, il ne déplace rien** :
zéro désaccord avec GNU Backgammon sur 10 920 000 couples, zéro empreinte différente sur
vingt-six graines. Fiche : [2026-09-17-T96-generateur-de-coups.md](2026-09-17-T96-generateur-de-coups.md).

**Mais l'épingle et les poids ne peuvent plus bouger l'un sans l'autre** : `7184e2f` ne contient
plus `cubeless_prob5_512_512_256_128.pt`, et les trois seuls échecs de la suite complète sous la
nouvelle épingle sont les tests d'environnement qui vérifient sa présence (1 836 tests passés
par ailleurs). Un dépôt épinglé à `7184e2f` servant les anciens poids aurait une provenance
qu'il ne saurait plus produire.

## Reproduire

```
python tools/export_model.py --model cubeless_prob5_512_512_256_256.pt \
    --out models/cubeless_prob5_512_512_256_256.bin

GN_MODEL_PT=vendor/backgammon-ai-engine/best_models/cubeless_prob5_512_512_256_256.pt \
GN_MODEL_BIN=models/cubeless_prob5_512_512_256_256.bin \
    python -m pytest tests/test_infer.py -q

python bench/measure_t70.py \
    --registry docs/corpus/t70/money-10000/registre-money.jsonl \
    --model models/cubeless_prob5_512_512_256_256.bin \
    --ply 2 --prune-k 0 --workers 35 \
    --out docs/mesures/t96-candidat-k0-t70.json
```

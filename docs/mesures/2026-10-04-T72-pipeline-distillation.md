# 2026-10-04 — T72 : le pipeline de distillation à 60–100 k MACs, prêt à lancer

**Fiche** : T72 (P3, réduire le réseau). **Nature de ce document** : un mode d'emploi et un
protocole. Il énonce des **mesures** là où il cite un chiffre daté, des **hypothèses** là où il le
dit. **Aucun entraînement long n'a été lancé** ; aucun poids n'est livré.

## Ce qui est livré

`tools/distill_t72.py`, un script unique, deux réseaux **de même forme, même graine, même part de
validation**, qui ne diffèrent que par leurs étiquettes :

| Réseau | Étiquettes | Méthode |
|---|---|---|
| **élève** | 2-ply de notre moteur (`tools/build_labels_t71.py`) et tête auxiliaire de volatilité | celle de `train_t71.py`, à la taille cible |
| **témoin redistillé** | 0-ply du grand réseau (`build/prune_corpus.npz`) | celle de `distill_smaller.py` |

La raison du témoin est dans `2026-09-03-T72prep-taille-et-distillation.md` : à taille égale, la
distillation seule coûte un facteur 3,2 (0,00313 → 0,00990). Un élève jugé contre l'original
attribuerait à la réduction une perte qui vient de la méthode. L'élève se lit **contre le
témoin**, jamais contre l'original seul.

**La cible de taille** : `--target-macs` (défaut 80 000) choisit l'échelle `(w, w/2, w/4)`, `w`
multiple de 16, la plus proche — 240-120-60, **83 340 MACs** (0,158 × la référence). `--shape`
impose une forme (256-128-64 = 91 456 MACs, le point central du balayage préparatoire). Une forme
hors de 60 000–100 000 MACs est refusée sauf `--allow-any-size`.

Artefacts, sous `--out-dir` (défaut `models/`) : `t72_student_<forme>.bin`,
`t72_witness_<forme>.bin` (format plat du moteur, écrits par `write_model`, relus par le moteur
à la fin du run) et `t72_<forme>.summary.json` (volumes, entropie retenue, graine, empreintes).

## Commande de lancement

Prérequis : `build/t71-money/` (étiquettes 2-ply, `tools/build_labels_t71.py`),
`build/prune_corpus.npz` (`tools/build_prune_corpus.py`), un GPU.

```
python tools/distill_t72.py --target-macs 80000 --labels build/t71-money \
    --witness-corpus build/prune_corpus.npz --out-dir models
```

Pour comparer à volume égal (recommandé) : ajouter `--limit N` avec N le plus petit des deux
corpus ; le sous-échantillon est tiré au sort, graine fixe. Sans lui, l'élève et le témoin ne
voient pas le même nombre de positions et la différence mêle méthode et volume.

Mode fumée (quelques centaines de lignes synthétiques, une époque, CPU, ~20 s) :
`python tools/distill_t72.py --smoke`. Il prouve la plomberie, **pas** la force : ses étiquettes
viennent d'un réseau tiré au sort.

## Durée estimée

* **Mesure** (T72prep, RTX 4090) : environ 3 minutes par réseau, 800 000 positions, 200 époques.
  Ici 300 époques au plus avec arrêt à 25 sans progrès, soit **de 3 à 6 minutes par réseau,
  environ 10 minutes pour la paire** — *hypothèse* : l'extrapolation n'a pas été chronométrée sur
  GPU.
* **Mesure** (CPU, 8 fils, machine chargée, 200 000 lignes aléatoires, un passage) : 70 µs par
  ligne et par époque pour 240-120-60, 102 µs pour 256-128-64. Sur CPU, 400 000 lignes × 300
  époques font donc **de 2,3 à 3,4 heures par réseau** au pire (arrêt précoce non compté) — c'est
  un plafond de repli, pas le chemin prévu.
* Jauge : environ deux minutes par réseau sur 30 processus (mesuré pour T72prep).

## Protocole de jauge

Instrument : celui de T70, `bench/measure_t70.py`, registre money arbitré
(10 000 décisions disputées), 2-ply, `prune_k = 12`. **Étalon** : l'incumbent 2-ply,
**0,00313** [0,00298 ; 0,00327].

```
for net in models/t72_student_*.bin models/t72_witness_*.bin; do
  python bench/measure_t70.py \
    --registry docs/corpus/t70/money-10000/registre-money.jsonl \
    --model "$net" --ply 2 --prune-model models/prune_32.bin --prune-k 12 \
    --workers 30 --out "docs/mesures/$(basename "$net" .bin)-t70.json"
done
```

Lecture :

1. Le chiffre qui compte est **élève − témoin**, avec son intervalle. Un intervalle qui contient
   zéro n'est pas une différence.
2. « Qualité indiscernable » de l'original (la cible de T72) se juge contre 0,00313 avec les deux
   intervalles ; le témoin dit seulement quelle part de l'écart vient de la méthode.
3. Une entropie croisée retenue plus basse ne dit **pas** que l'élève joue mieux (DS-14).

## Ce que ce pipeline ne règle pas

Il distille un réseau **statique**. T72prep a établi que la taille n'est pas le problème ; si
l'élève ne rejoint pas 0,00313, la cause est dans la méthode de distillation, et cette fiche ne
la corrige pas. L'élève n'est pas non plus quantifié (T73) : sa taille en octets et son débit se
mesurent à part.

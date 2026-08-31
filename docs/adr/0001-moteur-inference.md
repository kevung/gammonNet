---
status: accepted
date: 2026-08-03
tâche: T22
---

# Le moteur d'inférence est celui du dépôt de référence, et non un moteur tiers

`PLAN.md` ouvrait T22 comme un arbitrage entre deux candidats — le C d'Alexander Strehl et un
moteur d'inférence C++ tiers, complété du layout dense qu'il ne prend pas en charge. **Nous
retenons le premier**, et nous
**n'avons pas construit le second**, parce que la question que T22 devait trancher a reçu une
réponse mécanique plutôt que comparative.

## Ce qui a fait la décision

**Le gain du candidat est plafonné par arithmétique, pas par estimation.** Son argument de vitesse
est l'accumulation incrémentale NNUE, qui n'optimise que la couche d'entrée. Sur ce réseau, celle-ci
pèse **100 352 des 528 389 MACs, soit 19 %** — et le mode dense la désactive de toute façon
(`DenseFeatureLayout` : *« DENSE_FLOAT = 4 // Dense float input vector (NNUE disabled) »*). Aux
échecs le rapport est inverse, la couche d'entrée y écrasant tout le reste ; c'est de là que vient
la réputation de NNUE, et c'est pourquoi elle ne se transporte pas ici.

**Le vrai goulot était ailleurs, et il est levé.** `forward_raw` accumulait dans une variable
unique ; l'addition flottante n'étant pas associative, le compilateur ne pouvait ni dérouler ni
vectoriser. Lever l'interdiction a rendu **×4,1**, et le traitement par lot **×2,2** de plus, exact
au bit près — soit **×9 au total**, sans rien emprunter. Aucune de ces deux causes ne dépendait du
moteur : elles auraient frappé l'autre candidat de la même façon.

**Les trois briques qu'on aurait voulu lui déléguer n'y sont pas** : pas de packaging WebAssembly
de l'évaluateur (seule une bibliothèque de format de match l'est), une recherche de base **sans
filtrage de coups** — or c'est lui qui rend le 2-ply praticable — et des tables de fin de partie en
**stubs**. Elles sont à écrire dans les deux scénarios.

## Le critère d'acceptation, amendé et pourquoi

T22 exigeait que *« les deux candidats soient réellement mesurés, pas seulement discutés »*. **Le
second n'a pas été construit.** L'amendement est assumé : mesurer un plafond de 19 % sur la seule
partie qu'une architecture optimise, alors qu'on a déjà pris ×9 ailleurs, aurait coûté un à deux
jours pour confirmer un chiffre connu d'avance.

**Ce que cet amendement coûte, et il faut le savoir** : si le portage dense s'avérait un jour
apporter davantage que son plafond arithmétique — par un ordonnancement mémoire meilleur, par
exemple, indépendant de NNUE — nous ne le saurions pas. La décision est donc **révisable**, et le
chemin l'est aussi : `nn_dense_layout_supported()` accepte le layout `CUSTOM`, `nn_forward_dense()`
existe et est compilé, et l'extracteur manquant est notre T02, déjà écrit. Le mur est mince ; c'est
sa récompense qui est faible.

## Conséquences

- `src/gn_infer_reference.c` reste l'unique fichier propre au moteur. En changer, c'est réécrire ce
  `.c` et rien d'autre — l'isolation posée en T10 garde sa raison d'être.
- **Highway sort du périmètre.** Il n'arrivait que par transitivité, et sa double licence
  Apache-2.0 / BSD-3-Clause imposait des obligations propres. Si une vectorisation portable devient
  nécessaire, il sera pris à la source, comme dépendance nommée et non héritée.
- **La bibliothèque OGXM ne rentre pas.** C'était un piège de périmètre : un format de match, que
  `CLAUDE.md` range explicitement « ailleurs ».
- Les leviers restants sont dans **notre** code, et ils sont nommés : table de transposition,
  réseaux d'élagage pour la passe de classement, exploitation du lot dans la recherche.

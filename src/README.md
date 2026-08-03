# src/

La bibliothèque d'inférence : C/C++ pour le calcul, compilé pour **deux cibles** — natif
(profondeurs supérieures, rollouts) et WebAssembly via Emscripten (navigateur, 2-ply).

| Fichier | Rôle |
|---|---|
| `gn_rules.h` | L'interface : position, coups légaux, sentinelles. **Elle ne nomme aucun backend.** Lire le commentaire de convention avant de produire ou de consommer une `GnPosition` : une erreur d'orientation ne plante pas, elle produit des résultats plausibles et faux |
| `gn_rules_reference.c` | Son implémentation, adossée au moteur de règles de `backgammon-ai-engine` (MIT). **Tout ce qui est propre au backend vit là et nulle part ailleurs** — en changer, c'est réécrire ce seul fichier |

À venir : T02, le codec position ↔ vecteur de 196 caractéristiques — le goulot du projet.

## La frontière

> **Ce dépôt évalue une position. Il ne connaît pas ses appelants.**

Rien ici ne connaît d'utilisateur, de compte, de session ni de persistance. Une position
entre, une évaluation sort. Le stockage, la bibliothèque de parties, l'import de matchs et
l'interface sont **ailleurs**.

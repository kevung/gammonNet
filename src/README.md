# src/

La bibliothèque d'inférence : C/C++ pour le calcul, compilé pour **deux cibles** — natif
(profondeurs supérieures, rollouts) et WebAssembly via Emscripten (navigateur, 2-ply).

**Vide pour l'instant.** T00 ne produit aucune logique métier ; le premier code atterrit ici
avec T01 (représentation de position et coups légaux), puis T02 (le codec position ↔ vecteur
de 196 caractéristiques — le goulot du projet).

## La frontière

> **Ce dépôt évalue une position. Il ne connaît pas ses appelants.**

Rien ici ne connaît d'utilisateur, de compte, de session ni de persistance. Une position
entre, une évaluation sort. Le stockage, la bibliothèque de parties, l'import de matchs et
l'interface sont **ailleurs**.

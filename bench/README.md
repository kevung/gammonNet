# bench/

Les bancs de mesure. **Vide pour l'instant** — le premier est T05 (banc de débit), puis T21
(banc de débit navigateur).

## La règle qui gouverne ce répertoire

> **Une conclusion de performance se mesure, elle ne se déduit pas.**

Aucun chiffre de débit, de latence ou de taille ne se tire d'une lecture de code ni d'une
extrapolation. Tout rapport produit ici dit explicitement ce qui est **mesuré** et ce qui
reste **hypothèse** — la pénalité WebAssembly (estimée ×1,5 à ×2,5) est aujourd'hui une
hypothèse, et toute la frontière 2-ply / 3-ply en dépend.

Les rapports sont consignés dans `docs/mesures/`, avec leur date et leur configuration
exacte (`make env`).

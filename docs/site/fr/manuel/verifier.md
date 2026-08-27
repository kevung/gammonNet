# Vérifier l'artefact vous-même

L'archive contient de quoi contrôler qu'elle fait ce qu'elle annonce, **sans nous croire**.

## La parité avec le moteur de référence

```sh
node verify/parity.mjs
```

Il compare le module WebAssembly au moteur natif sur un repère de **2 000 positions**, et
**refuse** au-delà de 1e-6.

Attendu :

```
✅ scalaire   max|Δ| = 0.000e+0
✅ SIMD       max|Δ| = 6.407e-7
```

Le build scalaire est **exact**. Le build SIMD réassocie les sommes, d'où l'écart de 6,4e-7 —
borné, documenté, et sans effet sur le coup choisi.

## Les sommes de contrôle

```sh
sha256sum -c SHA256SUMS
```

Et le `sha256` des poids doit correspondre à celui inscrit dans `verify/*.provenance.json` — le
même depuis le premier jour du projet.

## Les mesures brutes

`evidence/` contient les données derrière chaque chiffre des notes de version :

| Fichier | Ce qu'il porte |
|---|---|
| `t3e-pr.json` | le taux d'erreur aux trois profondeurs, avec ses intervalles |
| `t3c-analyse-match.json` | les 139 décisions d'un vrai match, les deux moteurs |
| `t21b-navigateur-*.json` | le coût d'une décision et le parallélisme, dans un navigateur |
| `t3a-prune-search.json` | ce que l'élagage coûte et rapporte, par `k` |

Rien n'y est agrégé : ce sont les sorties des bancs, telles qu'ils les ont écrites.

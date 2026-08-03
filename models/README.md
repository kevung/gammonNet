# models/

Les poids. **Ce répertoire est gitignoré**, à deux exceptions près : ce fichier, et les
artefacts effectivement publiés (T50).

## Pourquoi gitignoré

Les poids du modèle de référence vivent déjà dans `vendor/backgammon-ai-engine/best_models/`,
récupérés à un commit épinglé par `tools/fetch_vendor.py`. Les recopier ici ferait deux
copies dont une finirait par mentir sur sa provenance.

Ce qui atterrit ici est **produit** : un `.bin` exporté par `export_weights.py`, ou un modèle
entraîné par nos soins (phase 4, conditionnelle).

## Nomenclature

Rappel de `BRIEF.md` §8 — **un réseau ne change de nom que si ses poids changent.** Ni le
couplage à une table de fin de partie, ni la compilation en WebAssembly, ni une conversion de
format n'en font un réseau nouveau.

| Niveau | Forme | Qui nomme |
|---|---|---|
| Réseau (les poids) | `strehl-prob5-512-512-256-128` | conserve la paternité de l'auteur |
| Configuration (réseau + recherche + fins de partie + équité de match) | `gammonNet 2-ply` | nous |

Un artefact publié porte donc `<réseau>_<version>_<date>.bin`, avec sa somme de contrôle et
des notes de version qui citent **le protocole, le volume et l'intervalle de confiance** de sa
mesure de force. Une version publiée sans mesure n'est pas publiable.

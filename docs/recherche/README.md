# `docs/recherche/` — les recherches approfondies

Ce répertoire contient **le plan** de la question « dépasser franchement gnubg tout en étant aussi
rapide ou plus rapide », et **quatorze prompts** prêts à être lancés en recherche approfondie
(*deep research*) dans Claude, dans un navigateur.

| Fichier | Rôle |
|---|---|
| [`00-plan-depasser-gnubg.md`](00-plan-depasser-gnubg.md) | Le plan : l'état mesuré, les quatre hypothèses de rupture, les vagues, ce que chaque recherche décide. **À lire en premier.** |
| `DS-01` … `DS-14` | Un prompt par recherche. Chacun est **autonome** : il porte son propre contexte, ses contraintes et son format de rendu. |
| [`retours/`](retours/) | Les rapports rendus, un fichier par recherche. |
| [`retours/MODELE.md`](retours/MODELE.md) | Ce qu'on attend d'un retour, et comment le classer. |

## Mode d'emploi

1. Ouvrir le fichier `DS-XX`, copier **tout le texte entre les deux lignes de démarcation** — et
   rien d'autre : ce qui est en dehors est une note interne au dépôt, elle n'a pas à partir dans
   la recherche.
2. Coller dans Claude, dans le navigateur, en activant la **recherche approfondie**.
3. Enregistrer le rapport rendu dans `docs/recherche/retours/DS-XX-retour.md`, en tête duquel on
   note **la date de la recherche** et le modèle utilisé.
4. Une fois une vague rentrée, relire `00-plan-depasser-gnubg.md` §7 : la vague suivante n'est pas
   à lancer telle quelle, elle est à **amender** avec ce que la précédente a appris. Chaque prompt
   de vague 2 ou 3 porte, en tête, la liste de ce qu'il faut y injecter.

## Les quatorze, dans l'ordre où les lancer

### Vague 1 — sans dépendance, à lancer ensemble

| | Fichier | Ce qu'elle décide |
|---|---|---|
| DS-01 | [`DS-01-etat-de-lart-des-moteurs.md`](DS-01-etat-de-lart-des-moteurs.md) | Où est réellement la barre, et si quelqu'un l'a déjà franchie |
| DS-02 | [`DS-02-anatomie-de-gnubg.md`](DS-02-anatomie-de-gnubg.md) | La cible de vitesse chiffrée, et où gnubg est documenté comme faible |
| DS-03 | [`DS-03-encodage-des-entrees.md`](DS-03-encodage-des-entrees.md) | Si l'encodage à 196 entrées plafonne ce que le réseau peut savoir |
| DS-05 | [`DS-05-recherche-stochastique.md`](DS-05-recherche-stochastique.md) | D'où viennent les évaluations économisables |
| DS-07 | [`DS-07-instrument-de-mesure.md`](DS-07-instrument-de-mesure.md) | Le protocole. **Prérequis, pas un choix** |
| DS-08 | [`DS-08-videau-au-dela-de-janowski.md`](DS-08-videau-au-dela-de-janowski.md) | Si le gain le moins cher est dans le videau |

### Vague 2 — après les retours dont chacune dépend

| | Fichier | Dépend de |
|---|---|---|
| DS-04 | [`DS-04-nnue-creux-quantification.md`](DS-04-nnue-creux-quantification.md) | DS-02, DS-03 |
| DS-06 | [`DS-06-entrainer-pour-la-recherche.md`](DS-06-entrainer-pour-la-recherche.md) | DS-01, DS-02 |
| DS-09 | [`DS-09-webassembly-et-webgpu.md`](DS-09-webassembly-et-webgpu.md) | DS-04 |
| DS-11 | [`DS-11-extreme-gammon-comme-reference.md`](DS-11-extreme-gammon-comme-reference.md) | DS-07 |
| DS-12 | [`DS-12-specialisation-et-melange-dexperts.md`](DS-12-specialisation-et-melange-dexperts.md) | DS-02, DS-03 |

Chacune porte, en tête, un tableau **« À injecter avant de lancer »** : les valeurs à substituer
dans le prompt aux endroits marqués `⟨…⟩`. Une recherche de vague 2 lancée sans ces substitutions
rendra un rapport générique.

### Vague 3 — conditionnelles

| | Fichier | Ne se lance que si |
|---|---|---|
| DS-10 | [`DS-10-corpus-et-donnees-libres.md`](DS-10-corpus-et-donnees-libres.md) | DS-06 retient un entraînement supervisé |
| DS-13 | [`DS-13-exactitude-course-et-fin-de-partie.md`](DS-13-exactitude-course-et-fin-de-partie.md) | La course pèse dans l'erreur totale |
| DS-14 | [`DS-14-budget-de-calcul.md`](DS-14-budget-de-calcul.md) | La vague 2 a désigné **une** architecture |

## Ce qui vaut pour les quatorze

Chaque prompt répète ces contraintes, parce qu'il doit tenir seul. Elles sont ici pour mémoire :

- **Licence.** Le module WebAssembly servi à un navigateur **est une distribution**. Poids de GNU
  Backgammon (GPL-3), réseaux HedgeHog (clause non commerciale), bgsage (AGPL-3) sont hors
  périmètre — y compris comme source d'entraînement.
- **gnubg est un instrument de mesure, jamais une source d'apprentissage.** Règle interne, plus
  stricte que le droit.
- **Pas de transcription de code ni de constantes réglées à la main.** On demande des mécanismes
  documentés, pas des extraits de source. Voir `docs/etudes/README.md`, le protocole à trois
  niveaux.
- **Une conclusion de performance se mesure.** Chaque affirmation d'un retour doit être étiquetée
  mesure ou hypothèse.
- **Le budget vient du client.** Une architecture se juge en précision **par MAC**, sur un
  téléphone.

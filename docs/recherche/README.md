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

### Vague 1 — **rentrée le 2026-08-27**, retours dans [`retours/`](retours/)

| | Fichier | Ce qu'elle décide | Retour |
|---|---|---|---|
| DS-01 | [`DS-01-etat-de-lart-des-moteurs.md`](DS-01-etat-de-lart-des-moteurs.md) | Où est réellement la barre, et si quelqu'un l'a déjà franchie | [rentré](retours/DS-01-retour.md) |
| DS-02 | [`DS-02-anatomie-de-gnubg.md`](DS-02-anatomie-de-gnubg.md) | La cible de vitesse chiffrée, et où gnubg est documenté comme faible | [rentré](retours/DS-02-retour.md) |
| DS-03 | [`DS-03-encodage-des-entrees.md`](DS-03-encodage-des-entrees.md) | Si l'encodage à 196 entrées plafonne ce que le réseau peut savoir | [rentré](retours/DS-03-retour.md) |
| DS-05 | [`DS-05-recherche-stochastique.md`](DS-05-recherche-stochastique.md) | D'où viennent les évaluations économisables | [rentré](retours/DS-05-retour.md) |
| DS-07 | [`DS-07-instrument-de-mesure.md`](DS-07-instrument-de-mesure.md) | Le protocole. **Prérequis, pas un choix** | [rentré](retours/DS-07-retour.md) |
| DS-08 | [`DS-08-videau-au-dela-de-janowski.md`](DS-08-videau-au-dela-de-janowski.md) | Si le gain le moins cher est dans le videau | [rentré](retours/DS-08-retour.md) |

Le bilan de la vague — hypothèses réévaluées, contradictions, corrections — est en **§11 du
[plan](00-plan-depasser-gnubg.md)**.

### Vague 2 — après les retours dont chacune dépend

| | Fichier | Dépend de | État |
|---|---|---|---|
| DS-04 | [`DS-04-nnue-creux-quantification.md`](DS-04-nnue-creux-quantification.md) | DS-02, DS-03 | **injecté le 2026-08-27, prêt à lancer** |
| DS-06 | [`DS-06-entrainer-pour-la-recherche.md`](DS-06-entrainer-pour-la-recherche.md) | DS-01, DS-02 | **injecté le 2026-08-27, prêt à lancer** |
| DS-09 | [`DS-09-webassembly-et-webgpu.md`](DS-09-webassembly-et-webgpu.md) | DS-04 | attend le retour de DS-04 |
| DS-11 | [`DS-11-extreme-gammon-comme-reference.md`](DS-11-extreme-gammon-comme-reference.md) | DS-07 | **injecté le 2026-08-27, prêt à lancer** |
| DS-12 | [`DS-12-specialisation-et-melange-dexperts.md`](DS-12-specialisation-et-melange-dexperts.md) | DS-02, DS-03 | **injecté le 2026-08-27, prêt à lancer** |

Chacune porte, en tête, un tableau **« À injecter avant de lancer »** : les valeurs à substituer
dans le prompt aux endroits marqués `⟨…⟩`. Pour DS-04, DS-06, DS-11 et DS-12, ces substitutions
**sont faites** — copier le texte entre les démarcations, tel quel. DS-09 attend encore les
siennes.

### Vague 3 — conditionnelles

| | Fichier | Ne se lance que si |
|---|---|---|
| DS-10 | [`DS-10-corpus-et-donnees-libres.md`](DS-10-corpus-et-donnees-libres.md) | DS-06 retient un entraînement supervisé |
| DS-13 | [`DS-13-exactitude-course-et-fin-de-partie.md`](DS-13-exactitude-course-et-fin-de-partie.md) | La course pèse dans l'erreur totale |
| DS-14 | [`DS-14-budget-de-calcul.md`](DS-14-budget-de-calcul.md) | La vague 2 a désigné **une** architecture |

## Ce qui vaut pour les quatorze

Chaque prompt répète ces contraintes, parce qu'il doit tenir seul. Elles sont ici pour mémoire :

- **Licence.** Le module WebAssembly servi à un navigateur **est une distribution**. Poids de GNU
  Backgammon (GPL-3) et réseaux HedgeHog (licence non confirmée, réputée non commerciale) sont
  hors périmètre — y compris comme source d'entraînement. bgsage est en réalité sous **MPL-2.0**
  (vérifié le 2026-08-27, et non AGPL-3 comme d'abord noté) : idées et benchmark réétudiables,
  pas de copie de code sans décision.
- **gnubg est un instrument de mesure, jamais une source d'apprentissage.** Règle interne, plus
  stricte que le droit.
- **Pas de transcription de code ni de constantes réglées à la main.** On demande des mécanismes
  documentés, pas des extraits de source. Voir `docs/etudes/README.md`, le protocole à trois
  niveaux.
- **Une conclusion de performance se mesure.** Chaque affirmation d'un retour doit être étiquetée
  mesure ou hypothèse.
- **Le budget vient du client.** Une architecture se juge en précision **par MAC**, sur un
  téléphone.

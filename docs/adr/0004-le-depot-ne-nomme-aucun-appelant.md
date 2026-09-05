---
status: accepted
date: 2026-09-05
portée: tout le dépôt — sources, tests, documentation, messages de commit à venir
---

# Le dépôt ne nomme aucun appelant, et ne s'adosse à aucun

`CLAUDE.md` pose depuis l'origine : *« ce dépôt évalue une position, il ne connaît pas ses
appelants »*. Rien ne vérifiait cette règle, et elle s'est érodée en huit jours au point que le
dépôt nommait deux appelants, inventoriait leurs fichiers, leur imputait leurs défauts, leur
prescrivait du travail, et adossait la justification de licence de sa table d'équité de match à
l'un d'eux.

**Décision : aucun appelant n'est nommé nulle part dans ce dépôt. Une mesure venue d'ailleurs
entre comme une MESURE ; jamais comme une RELATION.**

`CONTEXT.md` porte le vocabulaire que cette décision suppose — **cible** (à nous, se nomme),
**appelant** (anonyme par construction), **portage** (une origine de mesures), **source** et
**témoin**. `tests/test_frontier.py` la rend exécutable.

## Ce que la règle n'est pas

Elle n'interdit pas les faits venus d'ailleurs. « Un portage Go indépendant fait la même
décision en 0,277 s » est une donnée : elle a une date, un protocole, et elle reste. « Notre
consommateur doit reprendre ceci » est un lien de subordination : il part. La ligne passe entre
un chiffre et un ordre, pas entre l'ici et l'ailleurs.

Elle n'interdit pas non plus l'attribution. Une **source** — le rendu dont un nombre est lu —
crée une obligation de licence et doit être nommée. Ce que la règle refuse, c'est de nommer un
**témoin**, dont rien n'est dérivé.

## Les alternatives, et pourquoi elles ont été écartées

**Anonymiser les détails en gardant les noms.** Insuffisant : le nom seul suffit à révéler une
relation, et c'est le nom qui attire ensuite la prescription.

**Effacer jusqu'à l'existence d'un autre appelant.** Rejeté pour son coût probant. ADR-0003 tient
parce que le même changement conceptuel rend **+6,1 %** dans le `ProcessPoolExecutor` de
`python/gammonnet/arena.py` et **−50 %** sur le chemin `postMessage` du navigateur : deux
runtimes, deux cibles, tous deux ici. Mais T88 ne tient que parce qu'il existe *quelque part* une
autre écriture avec laquelle s'accorder. Nier cette existence transformerait des mesures en
opinions.

**Une liste noire de noms, vérifiée par un test.** Rejetée, et c'est le point le moins évident :
dans un dépôt public, une telle liste **dit plus que ce qu'elle empêche**. Elle annonce que ces
noms existent, qu'ils comptent, et qu'on les cache. Ce qui est vérifié à la place est une
**grammaire** — le dépôt parle de cibles et d'appelants anonymes — parce qu'une fois la grammaire
tenue, aucun nom nouveau ne peut entrer : il n'existe plus de phrase pour le porter.

## Ce que cela a coûté, en fait et pas en principe

**Un chemin de code a disparu.** `tools/extract_met.py` savait cloner un dépôt tiers pour y
parser une transcription Go de la table Kazaross-XG2. Ce chemin ne pouvait plus aboutir — depuis
#24, l'horizon exigé est de 25 entrées post-Crawford et cette transcription en portait 24 — mais
c'était surtout la forme la plus dure de la fuite : une dépendance **exécutable** envers un
appelant. Il ne reste qu'une source, `Kazaross-XG2.xml`, et son absence est maintenant une erreur
explicite au lieu d'un repli silencieux. Régénération complète après retrait :
`data/met_kazaross_xg2.json` et son empreinte SHA-256 **inchangés au bit près**.

**Une justification de licence a été remplacée.** L'embarquement de la table s'adossait au
« précédent MIT » d'un tiers. Le choix de licence d'un tiers n'autorise rien ; le fondement réel
était déjà écrit dans l'en-tête généré et se suffit — la table est l'œuvre de Neil Kazaross, GNU
Backgammon en est le véhicule de distribution et non l'auteur, et lire un fichier de données
n'est pas dériver d'un code. **Retirer la béquille rend l'argument plus fort.**

**Un contrôle a changé de nature, et y a gagné.** Un fichier de `wasm/`, nommé d'après un
appelant, mesurait l'écart avec une écriture externe pour qu'une substitution ailleurs soit un
fait chiffré. Cette raison n'existe plus ici — mais l'algorithme transcrit **est** le Position ID
gnubg, un format public, et
le fichier fait donc quelque chose que `codec_parity.mjs` ne sait pas faire : il traverse quatre
inversions de convention (26 cases contre 29, numérotation de Noir, positif Noir, joueur au trait
codé à l'envers) là où la parité compare deux écritures de même convention, qui se tromperaient
ensemble. Devenu `codec_conventions.mjs`, il est désormais lancé par `make wasm-codec` — il ne
l'était par aucune cible. Corpus T12, 2 050 positions : **0 écart**.

## Ce que cela ne répare pas

L'historique public est figé — décision prise le 2026-09-05, le dépôt étant utilisé depuis
plusieurs postes. Les noms restent dans les messages de commit et dans `git log -S`. Ce chantier
**arrête l'accumulation** et retire les noms de la surface que quelqu'un lit sans la chercher ;
il n'efface rien. La surface publiée — `docs/site/`, servi sur GitHub Pages, et l'artefact de
`dist/` — n'a jamais porté de nom d'appelant, et le README, qui en portait deux, n'en porte plus.

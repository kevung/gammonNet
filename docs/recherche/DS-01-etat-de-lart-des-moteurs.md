# DS-01 — L'état de l'art des moteurs de backgammon, et la qualité de leurs preuves

**Vague** 1 · **Dépend de** — · **Alimente** DS-06, DS-11, DS-12
**Ce qu'elle décide** : où est réellement la barre, et si quelqu'un a déjà franchi celle que nous
visons — auquel cas la question devient « comment », pas « est-ce possible ».

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides à cadrer un projet d'ingénierie appelé **gammonNet** : un évaluateur de positions de
backgammon (réseau de neurones + recherche expectiminimax + table d'équité de match + tables de
fin de partie exactes), compilé à la fois en WebAssembly pour tourner dans un navigateur, y
compris sur téléphone, et en natif pour les profondeurs supérieures et les rollouts.

**Où nous en sommes, en chiffres que nous avons mesurés nous-mêmes :** notre moteur est
statistiquement **équivalent à GNU Backgammon** en 2-ply, sur 50 000 paires de matchs de 7 points
(50,42 % de chances de gain de match, IC 95 % [50,16 ; 50,69]) et sur 50 000 paires de parties en
money (−0,0119 point par partie, IC contenant zéro). Notre réseau est meilleur que le sien au
0-ply (+0,00247 d'équité par décision) mais **cet avantage s'annule sous recherche** (+0,00007 au
2-ply, intervalle contenant zéro). Notre décision 2-ply coûte 25 à 60 fois plus cher que la
sienne.

**Ce que je veux faire maintenant : dépasser franchement GNU Backgammon en qualité d'analyse, tout
en étant aussi rapide ou plus rapide.** Avant d'engager des semaines de calcul, je veux savoir où
est vraiment la barre et ce que les autres ont déjà établi.

## La question

**Quel est l'état de l'art des moteurs de backgammon en 2026, et quelle est la qualité des preuves
qui soutient chaque classement ?**

## Les sous-questions, dans l'ordre d'importance

1. **Le classement, et ses preuves.** Recense les moteurs qui comptent — eXtreme Gammon (XG),
   GNU Backgammon, BGBlitz, HedgeHog, Snowie (historique), wildbg, `alexstrehl/backgammon-ai-engine`,
   et tout autre que tu trouves. Pour chacun : qui l'a écrit, dans quel état il est en 2026, ce
   qu'il revendique comme force, **et sur quelle mesure**. Distingue soigneusement une mesure
   publiée avec protocole et intervalle de confiance d'une affirmation de forum.
2. **Le plus grand écart documenté entre deux moteurs, et sa cause.** Quel est le plus gros écart
   de force **mesuré** entre deux moteurs modernes, en points par partie ou en PR ? Qu'est-ce que
   le moteur supérieur fait que l'autre ne fait pas — réseau plus gros, encodage plus riche,
   recherche plus profonde, meilleur videau, tables exactes ? C'est la sous-question la plus
   importante de cette recherche : je cherche **la cause d'un écart réel**, pas un palmarès.
3. **Quelqu'un a-t-il publiquement dépassé XG ?** Et sur quelle preuve ? Si des benchmarks
   publics existent (tables de round-robin, fichiers JSON de résultats, fils de forum avec
   protocole), rapporte-les **avec leurs chiffres et leurs volumes**.
4. **La littérature académique.** Que s'est-il publié sur le backgammon depuis TD-Gammon
   (Tesauro 1992-1995) ? En particulier : les travaux sur l'apprentissage par renforcement au
   backgammon post-2015, sur la recherche à nœuds de hasard, sur la décision de videau (dont
   Andrew Lin, *Learning Cube Strategy in Backgammon with Neural Networks*, TAAI 2020), et tout
   ce qui compare des architectures. Si un article est derrière un péage, dis-le et rapporte ce
   que le résumé, les citations et les versions préprint permettent d'établir.
5. **Les conventions de mesure de la communauté.** Comment cette communauté affirme-t-elle qu'un
   moteur est plus fort qu'un autre ? PR, taux d'erreur, mEMG, matchs dupliqués, rollouts de
   référence ? Quels volumes sont considérés comme concluants ? Quelles non-transitivités ont été
   observées entre moteurs (A bat B, B bat C, C bat A) ?
6. **Ce qui est répété sans avoir jamais été mesuré.** Le backgammon a une littérature de forum
   dense et recopiée. Signale explicitement les affirmations qui circulent partout sans source
   primaire — par exemple sur la force relative de XG et gnubg, ou sur ce que « 4-ply » apporte.

## Sources à ne pas manquer

- Les dépôts et sites : `alexstrehl/backgammon-ai-engine` (GitHub), `carsten-wenderdel/wildbg`
  (GitHub), `hedgehog-bg.com` et son GitLab public, le site de BGBlitz, `extremegammon.com`, le
  projet GNU Backgammon (`gnu.org/software/gnubg`) et ses listes de diffusion.
- Les fichiers de benchmarks publiés, s'il en existe (par exemple des JSON de round-robin servis
  par un site de moteur).
- Les forums : BGonline.org, r/backgammon, les archives de `rec.games.backgammon`, les fils
  techniques de GammOnLine.
- Google Scholar, arXiv, IEEE Xplore, ACM DL pour la partie académique.

## Ce qui ne m'intéresse pas

- Les conseils de jeu pour humains, les ouvertures, la stratégie du joueur.
- Les applications mobiles commerciales sans moteur documenté.
- Les comparaisons subjectives (« XG semble plus fort »).

## Contraintes, et pourquoi elles sont dures

Ce projet distribue un module WebAssembly à des navigateurs, ce qui **est une distribution** au
sens des licences. Donc :

- Tout artefact que tu me signales — code, poids, corpus, table — doit arriver **avec sa licence
  et son lien**. Un artefact sans licence identifiée m'est inutilisable.
- Sont hors périmètre, même en tant que source d'entraînement : les poids de GNU Backgammon
  (GPL-3), les réseaux HedgeHog (clause non commerciale), bgsage (AGPL-3).
- GNU Backgammon nous sert d'**oracle de mesure** et jamais de source d'apprentissage. C'est une
  règle que nous nous sommes donnée, plus stricte que ce que le droit exige.
- **Ne transcris aucun code source ni aucune constante réglée à la main** trouvée dans un moteur
  sous copyleft. Décris les mécanismes, cite la documentation.

## Format du rendu

Un rapport en **français**, structuré, où :

- **Chaque affirmation porte une étiquette** : `[MESURE]` (protocole, volume et intervalle
  publiés), `[MESURE FAIBLE]` (chiffre publié sans protocole ou sans volume), `[HYPOTHÈSE]`
  (raisonnement, extrapolation), `[FOLKLORE]` (circule sans source primaire).
- Chaque source est citée avec **son lien et la date à laquelle tu l'as consultée**.
- Une section **« Les contradictions entre sources »** : là où deux sources sérieuses ne disent
  pas la même chose, ne tranche pas — expose les deux et dis ce qui les départagerait.
- Une section **« Ce que je n'ai pas trouvé »**, explicite. Une absence documentée vaut mieux
  qu'une synthèse lisse.
- **Un tableau final de décision**, une ligne par piste que tu identifies :

  | Piste | Gain attendu (chiffré si possible) | Coût d'implémentation | Risque | Licence | La mesure qui trancherait |

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Pourquoi cette recherche est la première.** Tout le reste du programme suppose qu'il existe un
écart à combler ou une technique à emprunter. Si le retour montre que personne n'a jamais dépassé
XG et que gnubg est à quelques millièmes de PR du plafond connu, l'ambition « fortement dépasser »
change de nature : elle devient un travail de recherche, pas d'ingénierie, et le budget se discute
autrement.

**Le piège à surveiller au retour** : la table de benchmarks de HedgeHog (`benchmarks.json`) est
déjà dans `BRIEF.md` §5 et sert de repère au dépôt. Elle est produite par un acteur qui y figure.
Si le retour la reprend sans le dire, c'est une reprise, pas une confirmation indépendante.

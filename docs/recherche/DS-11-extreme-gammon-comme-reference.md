# DS-11 — eXtreme Gammon : la moitié de l'objectif qui n'a jamais été mesurée

**Vague** 2 · **Dépend de** DS-07 · **Alimente** le verdict final (T50)
**Ce qu'elle décide** : comment se comparer à XG — ou, si c'est impraticable, par quoi le
remplacer honnêtement dans l'énoncé de l'objectif.

---

## À injecter avant de lancer — ne pas coller cette section

**Injections faites le 2026-08-27**, depuis le retour DS-07. **Le prompt est prêt à lancer tel
quel.**

| Marqueur | Rempli depuis |
|---|---|
| `MÉTRIQUE` | DS-07, « Le protocole que je recommande » : perte d'équité appariée par position, arbitre externe escaladé en trois passes |
| `CORPUS` | DS-07, tableau des corpus : aucun corpus publié ne convient comme instrument — corpus maison figé, stratifié, versionné |

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon (réseau, recherche
expectiminimax, table d'équité de match, tables de fin de partie exactes), pour le navigateur et
le natif.

**L'objectif que le projet s'est donné, textuellement** : atteindre un niveau « équivalent ou
supérieur à GNU Backgammon **et à eXtreme Gammon** », et pouvoir le justifier par une mesure
reproductible.

**Où nous en sommes.** L'équivalence à GNU Backgammon en 2-ply est **mesurée et confirmée**
(50 000 paires de matchs, 50 000 paires de parties en money). **eXtreme Gammon n'a jamais été
mesuré** : nous n'avons aucun oracle XG, et toute notre chaîne d'arbitrage passe par gnubg. Cette
moitié de l'objectif est ouverte et ne se déduit pas de l'autre.

Nous avons par ailleurs arrêté un protocole de mesure : la **perte d'équité moyenne par décision,
appariée par position**, contre un arbitre externe dont la profondeur s'escalade en trois passes
(gnubg 3-ply partout ; rollout tronqué à réduction de variance quand l'écart meilleur/second est
inférieur à 0,05 ; rollout complet jusqu'à un intervalle de confiance à 95 % inférieur à 0,005
quand il reste inférieur à 0,02), les positions résolubles étant ancrées sur les bases exactes de
fin de partie ; le test statistique est un bootstrap par position, et le budget de rollout se
concentre sur les 10⁴ à 10⁵ décisions « disputées » où les moteurs divergent. Le corpus est un
**corpus maison figé, stratifié par classe de position et par contexte de score, et versionné**
(~50 000 positions) — aucun corpus publié ne convenait comme instrument.

## La question

**Que sait-on d'eXtreme Gammon techniquement, comment la communauté s'y compare-t-elle, et est-il
praticable d'en faire un oracle de mesure ?**

## Les sous-questions

### A. Ce qu'est XG, techniquement

1. **L'architecture, telle qu'elle est documentée publiquement.** Réseaux de neurones (combien,
   quelles tailles, quel encodage, si c'est dit), classes de position, recherche et profondeurs
   proposées, filtres de coups par réglage, tables de fin de partie embarquées, modèle de videau.
   Distingue soigneusement ce que l'éditeur documente de ce que la communauté suppose.
2. **Les niveaux d'analyse.** Que signifient exactement les réglages proposés (« XG Roller »,
   « XG Roller++ », les niveaux de rollout) en termes de profondeur et de nombre d'évaluations ?
   Combien de temps prend une décision à chaque niveau, sur quel matériel, si c'est publié ?
3. **La réduction de variance dans ses rollouts.** XG met en avant une réduction de variance. Ce
   qui en est documenté, et le facteur annoncé.

### B. La comparaison, telle qu'elle se pratique

4. **XG est-il plus fort que GNU Backgammon, et de combien ?** Je cherche des mesures avec
   protocole et volume, pas des impressions. À profondeur comparable et en temps comparable, que
   donnent les comparaisons publiées ? Existe-t-il des round-robins entre moteurs incluant XG,
   avec leurs chiffres bruts ?
5. **L'échelle de PR d'XG** — la formule exacte, ses constantes, et sa comparabilité avec le taux
   d'erreur de GNU Backgammon. (Si DS-07 l'a déjà établi, confirme ou corrige plutôt que de
   répéter.)
6. **Les usages d'XG comme référence dans la littérature technique** : quand un auteur écrit
   « PR 0,22 mesuré par XG++ », qu'a-t-il fait exactement ? Quelle chaîne d'outils, quel format de
   fichier, quel réglage ?

### C. La praticabilité — la partie qui décide

7. **Peut-on faire tourner XG comme oracle, en lot et sans interface ?** XG est un logiciel
   commercial Windows. Ce qui existe : analyse par lot, ligne de commande, importation et
   exportation de fichiers de match, formats de position (XGID), scriptage. Fonctionne-t-il sous
   Wine sur Linux, et quelqu'un l'a-t-il documenté ?
8. **Ce que la licence d'XG permet.** Lis les conditions d'utilisation publiées et dis
   explicitement : l'usage d'XG pour **analyser** des positions et publier les chiffres obtenus
   est-il permis ? L'usage automatisé en lot ? La comparaison publiée avec un autre moteur ? Je ne
   te demande pas un avis juridique, mais **ce que le texte dit**, cité.
9. **Les formats.** XGID (identifiant de position), les fichiers de match `.xg`, les exports
   d'analyse. Sont-ils documentés publiquement ? Existe-t-il des implémentations tierces sous
   licence permissive de lecture ou d'écriture de ces formats ?
10. **S'il est impraticable, par quoi le remplacer ?** Si l'usage d'XG comme oracle automatisé
    n'est pas praticable ou pas permis, quelles alternatives donnent une référence de force
    comparable : rollouts publiés de positions de référence, corpus analysés par XG et publiés par
    des tiers, comparaisons indirectes par un moteur commun ? **Cette sous-question est aussi
    importante que les autres** : une réponse « ce n'est pas praticable, voici le substitut
    honnête » est un résultat utile.

## Contraintes

- **Rien de non libre n'entre dans notre artefact distribué.** XG ne peut être qu'un **instrument
  de mesure** — jamais une source de poids, de table ni de données d'entraînement. Une
  recommandation qui reposerait sur l'emploi de ses données dans notre entraînement est
  inutilisable.
- Toute donnée, table ou corpus que tu signales arrive **avec ses conditions d'utilisation et son
  lien**.
- Distingue systématiquement **ce que l'éditeur publie** de **ce que la communauté suppose**. Ce
  domaine est riche en chiffres recopiés sans source primaire.

## Format du rendu

Un rapport en **français** où :

- Chaque affirmation porte une étiquette : `[ÉDITEUR]` (documentation officielle), `[MESURE]`
  (mesure tierce avec protocole), `[DÉCLARÉ]`, `[FOLKLORE]`.
- Chaque source porte son lien et sa date de consultation.
- Une section **« Le chemin praticable »** : la façon la plus simple de produire, chez nous, une
  comparaison chiffrée à XG — ou la déclaration argumentée qu'il n'y en a pas, avec le substitut
  recommandé.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Pourquoi cette recherche compte, alors qu'elle ne rend aucune force.** L'objectif du dépôt cite
XG nommément, et la fiche T35 conclut : « eXtreme Gammon : non mesuré. Aucun oracle XG n'existe
dans ce dépôt ; seul gnubg sert d'arbitre. Cette moitié de l'objectif reste ouverte et ne se déduit
pas de l'équivalence à gnubg. »

Deux issues, toutes deux acceptables :

1. **XG est utilisable comme oracle** — alors T50 peut rendre un verdict sur l'objectif tel qu'il
   est écrit.
2. **XG n'est pas utilisable** — alors il faut **réécrire l'objectif** dans `BRIEF.md`, avec la
   raison, plutôt que de laisser une moitié d'engagement pendante indéfiniment. Un objectif qu'on
   sait ne pas pouvoir mesurer doit être requalifié, pas oublié.

Ce qui serait une faute, c'est de conclure « au moins aussi fort que XG » par transitivité depuis
gnubg. Les non-transitivités entre moteurs de styles différents sont réelles et documentées —
c'est même la raison pour laquelle le dépôt a choisi le round-robin plutôt qu'un classement.

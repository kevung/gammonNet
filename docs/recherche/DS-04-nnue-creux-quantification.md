# DS-04 — Encodage creux, accumulation incrémentale, quantification : d'où vient un ×10

**Vague** 2 · **Dépend de** DS-02 et DS-03 · **Alimente** DS-09, DS-12, DS-14
**Ce qu'elle décide** : si le poste « arithmétique » (×2 à ×4) et le poste « taille de réseau »
(×4 à ×16) peuvent être pris ensemble par un changement d'architecture d'inférence.

---

## À injecter avant de lancer — ne pas coller cette section

Cette recherche n'est lançable qu'une fois DS-02 et DS-03 rentrées. Trois valeurs à substituer
dans le prompt, aux endroits marqués `⟨…⟩` :

| Marqueur | À remplir depuis |
|---|---|
| `⟨MACS-GNUBG⟩` | DS-02, tableau des tailles de réseau — le nombre de MACs par évaluation du réseau `contact` de gnubg |
| `⟨VERDICT-CREUX⟩` | DS-03, section « L'encodage que je recommanderais » — une phrase disant si un encodage **creux binaire** est jugé viable pour le backgammon, ou si les caractéristiques utiles sont denses et calculées |
| `⟨CARACTÉRISTIQUES⟩` | DS-03, catalogue — les trois à cinq caractéristiques candidates retenues, avec leur nature (creuse ou dense) |

Si `⟨VERDICT-CREUX⟩` est négatif — les caractéristiques utiles sont denses —, la sous-question 1
du prompt devient secondaire et les sous-questions 4 à 7 (quantification, noyaux, distillation)
deviennent l'essentiel. **Réordonne le prompt en conséquence avant de le lancer** : une recherche
approfondie suit l'ordre qu'on lui donne.

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon : réseau de neurones,
recherche expectiminimax, tables de fin de partie exactes. Deux cibles : **WebAssembly** dans un
navigateur, y compris sur téléphone, et natif.

**Le réseau, aujourd'hui.** 196 entrées **denses** en flottants (encodage de Tesauro : 24 points ×
4 unités « thermomètre » par joueur, plus barre et pions sortis), puis 512 → 512 → 256 → 128 → 5
sorties sigmoïdes. Environ **527 000 multiplications-accumulations par évaluation**, en `float32`,
avec un noyau qui traite les positions par lots de 32.

**Le problème, chiffré.** Notre décision 2-ply coûte ~2,0 s mono-fil ; celle de GNU Backgammon
~10 ms. Nous sommes **25 à 60 fois plus lents**. Le réseau de gnubg fait, lui, ⟨MACS-GNUBG⟩ MACs
par évaluation. Une évaluation nous coûte de l'ordre de **60 à 90 µs** mono-fil, soit ~8 GMAC/s
sur un cœur — donc le noyau n'est pas absurde, il calcule simplement beaucoup trop.

**Ce que je cherche : un facteur 10 ou plus sur le coût d'une évaluation, à qualité égale.**

Une piste m'intéresse particulièrement, et je veux savoir si elle tient. Aux échecs, les moteurs
modernes emploient une architecture dite **NNUE** : une première couche très large alimentée par
des entrées **binaires creuses**, dont l'accumulateur est **mis à jour de façon incrémentale**
quand la position change peu, suivie de petites couches en arithmétique entière. Le gain vient de
ce que la première couche — l'essentiel des MACs — n'est presque jamais recalculée en entier.

Au backgammon, un coup ne modifie que **2 à 4 points du plateau** sur 26. La mise à jour
incrémentale semble donc très applicable — mais notre encodage actuel est **dense**, ce qui
l'exclut par construction. Une étude d'encodage que j'ai fait mener conclut : ⟨VERDICT-CREUX⟩ ;
les caractéristiques candidates retenues sont ⟨CARACTÉRISTIQUES⟩.

## La question

**Comment évaluer un petit réseau de valeur 10 fois plus vite, sur processeur et en WebAssembly,
sans perdre de qualité — et l'architecture NNUE s'applique-t-elle à un jeu à dés ?**

## Les sous-questions

1. **NNUE, précisément.** Quelle est l'architecture réelle (tailles de couche, types entiers,
   facteurs d'échelle, fonction d'activation à écrêtage) ? **Quelle fraction des MACs est
   effectivement économisée par l'accumulation incrémentale**, et sous quelles conditions ?
   Quelles sont les contraintes structurelles : combien de caractéristiques peuvent changer par
   coup avant que la mise à jour incrémentale cesse d'être rentable ? Comment gère-t-on le
   changement de trait ?
2. **NNUE hors des échecs.** A-t-elle été portée au shogi (son origine), aux dames, à d'autres
   jeux, et **à un jeu à hasard** ? Quels résultats sont publiés ? Si personne ne l'a fait pour un
   jeu à dés, dis-le explicitement — c'est une information.
3. **Le cas particulier de l'expectiminimax.** Dans notre recherche, un nœud développe **21 jets**
   depuis la même position parente, et chaque jet produit ~20 positions filles. Toutes ces filles
   partagent l'essentiel de leur plateau avec la parente. Est-ce que cela rend l'accumulation
   incrémentale **plus** rentable qu'aux échecs (beaucoup de positions filles proches d'une même
   parente) ou **moins** (les positions sont évaluées par lots, et un lot de 32 positions
   indépendantes se calcule bien de façon dense) ? Y a-t-il des travaux sur l'arbitrage
   « incrémental contre par lots » ?
4. **La quantification.** Pour de petits perceptrons multicouches (moins d'un million de
   paramètres) : que perd-on en précision en passant en `int8` ou `int16` ? Quantification
   post-entraînement contre entraînement conscient de la quantification — quels écarts sont
   **mesurés** ? Quel gain de débit réel, et non théorique, sur processeur ?
5. **Les noyaux.** Quel débit atteint-on en pratique pour un produit matrice-vecteur ou
   matrice-matrice de cette taille, en `int8` avec AVX2 / AVX-512 VNNI, en NEON avec `dotprod`, et
   en WebAssembly SIMD128 ? Existe-t-il des bibliothèques **sous licence permissive** (MIT, BSD,
   Apache-2.0) qui font ce travail ? Attention : le code NNUE de Stockfish est sous **GPL-3** et
   nous est donc inutilisable — signale ce genre de piège plutôt que de me le recommander.
6. **Les autres voies vers le même facteur.** Distillation vers un réseau plus petit (quelle perte
   pour quel facteur de taille, sur de petits réseaux de valeur ?), élagage structuré,
   factorisation de rang faible, partage de couches entre classes de position, `float16` et
   `bfloat16`. Y a-t-il des courbes publiées **précision contre MACs** pour de petits réseaux de
   valeur dans les jeux ?
7. **La reproductibilité au bit près.** Nous tenons à ce que le moteur natif et le moteur
   WebAssembly rendent **le même résultat au bit près** (nous avons déjà dû désactiver la
   contraction FMA pour cela). Qu'est-ce que la quantification entière change à cette propriété —
   la rend-elle plus facile (arithmétique exacte) ou introduit-elle d'autres écarts (ordres de
   sommation, saturation) ?

## Contraintes

- **Licence, bloquante.** Nous distribuons un module WebAssembly, ce qui est une distribution.
  Toute bibliothèque ou tout code que tu signales doit arriver **avec sa licence**. Le copyleft
  fort (GPL, AGPL) est exclu de l'artefact ; Apache-2.0 et BSD sont acceptables avec leurs
  obligations propres (notice, marquage des fichiers modifiés).
- **Chiffre les gains, en distinguant théorique et mesuré.** « L'int8 est 4 fois plus rapide » est
  une borne théorique ; ce qui m'intéresse est ce qu'un banc a réellement rendu, avec la taille de
  réseau et le processeur.
- Le budget vient du **client** : une architecture se juge en précision **par MAC**, sur un
  téléphone. Un réseau meilleur et plus lent est un échec.

## Format du rendu

Un rapport en **français** où :

- Chaque affirmation porte une étiquette : `[MESURE]` (banc publié, avec matériel et tailles),
  `[THÉORIQUE]` (borne arithmétique), `[DÉCLARÉ]`, `[HYPOTHÈSE]`.
- Chaque source porte son lien et sa date de consultation.
- **Un tableau des voies vers le facteur 10** :

  | Voie | Facteur attendu | Perte de qualité | Effort | Licence des briques | Compatible WebAssembly ? | Compatible bit-à-bit ? |

- Une section **« L'architecture d'inférence que je recommanderais »**, décrite assez précisément
  pour être implémentée : tailles, types, disposition mémoire, forme du noyau.
- Une section **« Ce que je n'ai pas trouvé »**, et en particulier : dis-moi franchement si
  personne n'a jamais appliqué l'accumulation incrémentale à un jeu à dés.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**L'histoire de cette question dans le dépôt, qu'il faut avoir en tête au retour.** `BRIEF.md` §3.2
a déjà écarté NNUE, et pour une raison chiffrée : sur les ~527 000 MACs de notre réseau, la couche
d'entrée que l'accumulation optimise n'en porte que **19 %** — aux échecs, le rapport est inverse.
La conclusion était juste **pour notre architecture actuelle**.

Ce que DS-04 rouvre est différent : ce n'est pas « ajouter NNUE à notre réseau », c'est
**redessiner le réseau pour que NNUE ait du sens** — une première couche large et creuse portant
80 % des MACs, incrémentale, suivie de peu de choses. C'est l'inversion du rapport qui est en
jeu, pas le placage d'une technique.

Le risque de cette recherche est qu'elle revienne enthousiaste sur une architecture que rien ne
valide dans un jeu à dés. La sous-question 3 est là pour cela, et **la dernière ligne du format de
rendu est délibérée** : une réponse « personne ne l'a fait » est un résultat exploitable, une
réponse enthousiaste sans référence ne l'est pas.

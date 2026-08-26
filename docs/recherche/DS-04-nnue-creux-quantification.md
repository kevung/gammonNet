# DS-04 — Encodage creux, accumulation incrémentale, quantification : d'où vient un ×10

**Vague** 2 · **Dépend de** DS-02 et DS-03 · **Alimente** DS-09, DS-12, DS-14
**Ce qu'elle décide** : si le poste « arithmétique » (×2 à ×4) et le poste « taille de réseau »
(×4 à ×16) peuvent être pris ensemble par un changement d'architecture d'inférence.

---

## À injecter avant de lancer — ne pas coller cette section

**Injections faites le 2026-08-27**, depuis les retours DS-02 et DS-03. Le verdict « creux » de
DS-03 est **négatif** — les caractéristiques utiles sont des grandeurs calculées denses, et le
gain de l'accumulateur incrémental est jugé faible pour une évaluation statique par lots. Le
prompt a donc été **réordonné** comme l'exigeait cette section : quantification, noyaux et
distillation d'abord (sous-questions 1 à 4), NNUE ensuite (5 à 7). **Le prompt est prêt à lancer
tel quel.**

| Marqueur | Rempli depuis |
|---|---|
| `MACS-GNUBG` | DS-02 : contact 250 → 128 → 5 = **~32 640 MACs** ; réseau d'élagage ~2 550 MACs aux nœuds internes |
| `VERDICT-CREUX` | DS-03, « L'encodage que je recommanderais » et sous-question 4 |
| `CARACTÉRISTIQUES` | DS-03, catalogue — tranche A |

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
~10 ms. Nous sommes **25 à 60 fois plus lents**. Le réseau de gnubg fait, lui, environ
**32 640 MACs** par évaluation (250 entrées → 128 cachées → 5 sorties, soit ~16 fois moins que
nous), et il n'en dépense qu'environ **2 550** aux nœuds internes de sa recherche, via un petit
réseau d'élagage d'une dizaine de neurones cachés. Une évaluation nous coûte de l'ordre de
**60 à 90 µs** mono-fil, soit ~8 GMAC/s sur un cœur — donc le noyau n'est pas absurde, il calcule
simplement beaucoup trop.

**Ce que je cherche : un facteur 10 ou plus sur le coût d'une évaluation, à qualité égale.**

Une étude d'encodage que j'ai fait mener conclut que l'encodage **creux binaire** à la NNUE n'est
pas la voie naturelle au backgammon : les caractéristiques qui portent l'information utile sont
des grandeurs calculées **denses** (nombre de tirs touchant un ou deux blots, pips attendus
perdus, échappées et containment du pion arriéré via tables précalculées, timing, qualité de
prime — toutes en O(24 cases) ou O(36 tirs)), et le gain de l'accumulateur incrémental est jugé
faible pour une recherche expectiminimax qui évalue des positions statiques par lots plutôt qu'un
chemin make/unmake profond. La seule idée NNUE retenue par cette étude est la
**sur-paramétrisation creuse de la première couche** : beaucoup d'entrées, première couche large,
couches suivantes petites. **L'essentiel de ma question porte donc sur la quantification, les
noyaux et la réduction du réseau ; NNUE n'est qu'une piste secondaire à vérifier.**

## La question

**Comment évaluer un petit réseau de valeur 10 fois plus vite, sur processeur et en WebAssembly,
sans perdre de qualité — et accessoirement, l'architecture NNUE s'applique-t-elle à un jeu à dés ?**

## Les sous-questions

1. **La quantification.** Pour de petits perceptrons multicouches (moins d'un million de
   paramètres) : que perd-on en précision en passant en `int8` ou `int16` ? Quantification
   post-entraînement contre entraînement conscient de la quantification — quels écarts sont
   **mesurés** ? Quel gain de débit réel, et non théorique, sur processeur ?
2. **Les noyaux.** Quel débit atteint-on en pratique pour un produit matrice-vecteur ou
   matrice-matrice de cette taille, en `int8` avec AVX2 / AVX-512 VNNI, en NEON avec `dotprod`, et
   en WebAssembly SIMD128 ? Existe-t-il des bibliothèques **sous licence permissive** (MIT, BSD,
   Apache-2.0) qui font ce travail ? Attention : le code NNUE de Stockfish est sous **GPL-3** et
   nous est donc inutilisable — signale ce genre de piège plutôt que de me le recommander.
3. **Les autres voies vers le même facteur.** Distillation vers un réseau plus petit (quelle perte
   pour quel facteur de taille, sur de petits réseaux de valeur ?), élagage structuré,
   factorisation de rang faible, partage de couches entre classes de position, `float16` et
   `bfloat16`. Y a-t-il des courbes publiées **précision contre MACs** pour de petits réseaux de
   valeur dans les jeux ?
4. **La reproductibilité au bit près.** Nous tenons à ce que le moteur natif et le moteur
   WebAssembly rendent **le même résultat au bit près** (nous avons déjà dû désactiver la
   contraction FMA pour cela). Qu'est-ce que la quantification entière change à cette propriété —
   la rend-elle plus facile (arithmétique exacte) ou introduit-elle d'autres écarts (ordres de
   sommation, saturation) ?
5. **NNUE, précisément.** Aux échecs, les moteurs modernes emploient une première couche très
   large alimentée par des entrées binaires creuses, dont l'accumulateur est mis à jour de façon
   incrémentale quand la position change peu, suivie de petites couches en arithmétique entière.
   Quelle est l'architecture réelle (tailles de couche, types entiers, facteurs d'échelle,
   fonction d'activation à écrêtage) ? **Quelle fraction des MACs est effectivement économisée
   par l'accumulation incrémentale**, et sous quelles conditions ? Combien de caractéristiques
   peuvent changer par coup avant que la mise à jour incrémentale cesse d'être rentable ? Comment
   gère-t-on le changement de trait ?
6. **NNUE hors des échecs.** A-t-elle été portée au shogi (son origine), aux dames, à d'autres
   jeux, et **à un jeu à hasard** ? Quels résultats sont publiés ? Si personne ne l'a fait pour un
   jeu à dés, dis-le explicitement — c'est une information.
7. **Le cas particulier de l'expectiminimax.** Dans notre recherche, un nœud développe **21 jets**
   depuis la même position parente, et chaque jet produit ~20 positions filles. Toutes ces filles
   partagent l'essentiel de leur plateau avec la parente. Est-ce que cela rend l'accumulation
   incrémentale **plus** rentable qu'aux échecs (beaucoup de positions filles proches d'une même
   parente) ou **moins** (les positions sont évaluées par lots, et un lot de 32 positions
   indépendantes se calcule bien de façon dense) ? Y a-t-il des travaux sur l'arbitrage
   « incrémental contre par lots » ?

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

# DS-03 — L'encodage : les entrées qui portent la stratégie

**Vague** 1 · **Dépend de** — · **Alimente** DS-04, DS-06, DS-12
**Ce qu'elle décide** : si l'hypothèse H2 tient — notre avantage 0-ply s'annule sous recherche
parce que le réseau ignore ce que la recherche redécouvre — et quelles entrées ajouter.

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon : réseau de neurones,
recherche expectiminimax, table d'équité de match, tables de fin de partie exactes. Il est compilé
en WebAssembly pour tourner dans un navigateur (y compris sur téléphone) et en natif pour les
rollouts.

**Notre encodage aujourd'hui**, hérité de Tesauro et repris tel quel du modèle que nous employons
(sous licence MIT) : **196 nombres flottants**, toujours du point de vue du joueur au trait.

```
Bloc MOI        (98) : 24 points × 4 unités « thermomètre » = 96
                       ma barre / 2,0                       =  1
                       mes pions sortis / 15,0              =  1
Bloc ADVERSAIRE (98) : idem
```

Le réseau derrière fait 196 → 512 → 512 → 256 → 128 → 5 sorties (probabilités imbriquées de gain,
gain-gammon, gain-backgammon, perte-gammon, perte-backgammon), soit ~527 000
multiplications-accumulations par évaluation.

**Le fait qui motive cette recherche.** Nous avons mesuré, sur 2 400 décisions de contact et avec
deux arbitres indépendants, que notre réseau bat celui de GNU Backgammon de **+0,00247 d'équité
par décision au 0-ply**, mais que cet avantage tombe à **+0,00007 au 2-ply** — intervalle de
confiance contenant zéro. **La recherche efface l'avantage du réseau.** Mon interprétation, que je
veux mettre à l'épreuve : deux plies de recherche *retrouvent* précisément l'information que
l'encodage brut ne donne pas au réseau. GNU Backgammon, lui, utilise ~250 entrées dont des
caractéristiques stratégiques **calculées**, et non un simple compte de pions par point.

## La question

**Quelles représentations d'entrée ont été publiées pour le backgammon, lesquelles sont
mesurément meilleures, et à quel coût par MAC ?**

## Les sous-questions

1. **L'inventaire des encodages publiés.** Tesauro (Neurogammon, TD-Gammon 1.0 puis 2.0/3.0 et
   ses « caractéristiques expertes »), GNU Backgammon, Berliner (BKG et ses fonctions
   d'application floue), Snowie si documenté, `wildbg`, HedgeHog, `alexstrehl/backgammon-ai-engine`,
   et tout autre. Pour chacun : le nombre d'entrées, leur nature, et **ce que l'auteur dit avoir
   gagné** en les ajoutant.
2. **La preuve que les caractéristiques calculées valent le coup.** Tesauro rapporte que
   TD-Gammon a gagné en force quand il a ajouté des caractéristiques expertes à l'encodage brut.
   Quel était le gain exact, mesuré comment ? Existe-t-il d'autres ablations publiées, sur le
   backgammon ou sur d'autres jeux à hasard, qui **chiffrent** l'apport d'une caractéristique
   calculée par rapport à un encodage brut à capacité égale ?
3. **La liste des grandeurs stratégiques calculables.** Je veux un catalogue, avec pour chacune sa
   définition mathématique exacte et son coût de calcul :
   - exposition : nombre de blots, **nombre de tirs qui les touchent**, tirs pondérés par la
     perte attendue ;
   - blocage : longueur d'un prime, points consécutifs, « force du blocage » devant un pion
     arriéré, nombre de points du jan intérieur ;
   - conteneur et ancre : points d'ancre tenus, position du pion le plus arriéré ;
   - course : compte de pips, **EPC** (*effective pip count*), compte de Kleinman, compte de
     Thorp, compte de Trice — et ce qu'ils prédisent réellement ;
   - timing : réserve de coups jouables, risque de crash ;
   - contact : présence de contact, nombre de croisements restants.
   Pour chacune : est-elle déjà **implicitement** calculable par un réseau à partir des 196
   entrées brutes, ou demande-t-elle une composition que trois couches ne trouvent pas ?
4. **Les alternatives modernes à l'encodage plat.** Que donnerait, pour un plateau de 26 cases :
   un encodage **creux binaire** (indicatrices d'occupation, à la manière des encodages NNUE aux
   échecs), des plongements par point, une convolution 1-D sur le plateau, une attention sur les
   26 cases, une représentation relative au pion arriéré ? Y a-t-il des résultats publiés, au
   backgammon ou sur des jeux voisins, qui les comparent **à budget de MACs égal** ?
5. **La question qui décide.** Existe-t-il des travaux — au backgammon ou dans d'autres jeux — qui
   montrent qu'**un encodage plus riche réduit le bénéfice de la recherche** ? Autrement dit :
   l'information que la recherche « redécouvre » peut-elle être mise dans l'entrée, et cela
   a-t-il déjà été mesuré ? C'est exactement notre hypothèse, et je cherche à savoir si elle a
   déjà été testée par quelqu'un.
6. **La symétrie et les invariances.** Notre encodage est déjà relatif au joueur au trait. Y a-t-il
   d'autres invariances exploitables (symétrie miroir, invariance par translation d'une course) et
   quelqu'un a-t-il mesuré ce qu'elles rapportent ?

## Ce qui ne m'intéresse pas

- Les conseils de jeu pour humains, sauf lorsqu'une notion stratégique est **définie assez
  précisément pour être calculée** (auquel cas elle m'intéresse beaucoup).
- Les architectures très grandes : notre contrainte de taille vient du **navigateur d'un
  téléphone**, jamais de la machine d'entraînement. Une entrée qui coûte 50 000 MACs à calculer ne
  sert à rien.

## Contraintes

- Nous distribuons un module WebAssembly, ce qui **est une distribution**. Tout artefact que tu
  signales (code, poids, corpus) doit venir **avec sa licence et son lien**. Hors périmètre, même
  comme source d'entraînement : poids de GNU Backgammon (GPL-3), réseaux HedgeHog (clause non
  commerciale), bgsage (AGPL-3).
- **Ne recopie aucun code source de ces projets, ni aucune constante réglée à la main.** Une
  *idée* documentée est réimplémentable ; du code transcrit, même traduit dans un autre langage,
  ne l'est pas. Décris les mécanismes et cite la documentation.

## Format du rendu

Un rapport en **français** où :

- **Chaque affirmation porte une étiquette** : `[MESURE]` (ablation publiée avec protocole et
  volume), `[DÉCLARÉ]` (un auteur l'affirme sans mesure jointe), `[HYPOTHÈSE]`, `[FOLKLORE]`.
- Chaque source porte son lien et la date de consultation.
- **Un catalogue de caractéristiques candidates**, une ligne par caractéristique :

  | Caractéristique | Définition exacte | Coût de calcul | Déjà déductible des 196 entrées ? | Preuve de son apport | Origine et licence de l'idée |

- Une section **« L'encodage que je recommanderais »** : une proposition chiffrée — combien
  d'entrées, lesquelles, quel surcoût en MACs sur la première couche, et **quelle ablation nous
  devrions faire tourner en premier** pour la valider ou l'écarter.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**Le lien avec la vitesse, qu'il ne faut pas perdre.** Ajouter 60 entrées denses sur une première
couche de 512 coûte ~31 000 MACs, soit +6 % — négligeable. Mais si DS-03 conclut qu'un encodage
**creux** est préférable, alors DS-04 change complètement de forme : l'accumulation incrémentale
de type NNUE devient applicable, et le poste dominant du moteur devient adressable. C'est pour
cela que DS-04 attend ce retour.

**Le contrôle interne à faire au retour.** Le dépôt possède déjà l'instrument qui teste H2 :
`bench/decision_loss.py` mesure la perte d'équité par décision à profondeur égale, avec deux
arbitres. Une caractéristique candidate se valide en réentraînant à tronc gelé et en rejouant ce
banc — quelques heures, pas des semaines. Toute recommandation de ce retour qui ne se teste pas
ainsi doit être regardée deux fois.

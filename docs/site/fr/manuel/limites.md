# Ce qu'il faut savoir avant de s'en servir

## La force, telle qu'elle est mesurée

**Équivalent à GNU Backgammon en 2-ply.** −0,0119 ppg [−0,0310 ; +0,0074] sur 50 000 paires en
money ; 50,42 % de MWC [50,16 ; 50,69] sur 50 000 paires en match de 7 points.

**« Supérieur » n'est pas établi.** **eXtreme Gammon n'a pas été mesuré.**

## Les quatre choses qui changent le résultat

1. **Le réglage d'élagage.** À `k = 3` le moteur va deux fois plus vite qu'à 12 et perd
   **dix-huit fois** ce qu'un ply entier de profondeur rapporte. Ne le baissez pas sans mesurer.
2. **Le pool de workers.** Sans lui, un match prend 350 s au lieu de 74.
3. **Le score et le videau.** Une position ne se joue pas pareil en money et à 2-away. Si vous ne
   les passez pas, vous obtenez une analyse *money*, quelle que soit la vraie situation.
4. **La table exacte de fin de partie n'est pas fournie** — elle pèse 1,2 Gio. La fin de partie
   retombe donc sur le réseau, ce qui coûte **0,00028 d'équité par décision de bearoff**. Le pire
   cas mesuré vaut 0,0919 sur une seule décision : c'est la queue qui coûte, pas la moyenne.

## Ce que le moteur refuse de faire

Il **refuse** plutôt que d'approximer, et c'est délibéré :

- Un modèle qu'il ne sait pas évaluer est **refusé** — pas chargé « au mieux ».
- Un score hors de la table d'équité de match **arrête** l'analyse — il ne retombe pas
  silencieusement en money.
- Une position illisible rend une erreur, pas une évaluation plausible.

La raison est le mode de défaillance central du domaine : **un réseau à qui l'on donne une entrée
qu'il n'a jamais vue retourne cinq probabilités parfaitement plausibles**. Un refus bruyant vaut
mieux qu'un chiffre faux.

## Ce que le projet ne fait pas

gammonNet **évalue une position**. Il ne lit pas de fichiers de match, ne gère ni parties ni
utilisateurs, et n'a pas d'interface. Une position entre, une évaluation sort. Pour analyser un
match, faites-le lire par un logiciel qui sait le faire et passez les positions.

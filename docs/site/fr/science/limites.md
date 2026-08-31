# Les hypothèses et les limites

Cette page se veut **exhaustive**. Elle liste ce que le projet suppose, ce qu'il n'a pas mesuré, et
ce qu'il a mesuré à son désavantage. Une documentation qui ne contiendrait que les bonnes nouvelles
ne serait pas une preuve.

## Ce qui n'est pas mesuré

| | Pourquoi |
|---|---|
| **eXtreme Gammon** | Aucun oracle XG n'existe dans ce dépôt. Cette moitié de l'objectif ne se déduit pas de l'équivalence à GNU Backgammon |
| **« Supérieur » à GNU Backgammon** | L'écart de +0,0400 ppg mesuré en cubeless ne se reproduit pas une fois le videau branché |
| **La force de la configuration élaguée** | Bornée à ~0,028 ppg sur 10 000 paires, pas résolue : l'effet attendu (~0,013) est la moitié de l'intervalle |
| **Le PR sur un mélange réaliste** | Le corpus est uniquement de contact ; le PR mesuré est **probablement pessimiste**, sans que l'écart soit chiffré |
| **Le budget mobile** | La pénalité mesurée en août était de ×2,12 à ×2,83 sur deux appareils, non rejouée depuis les optimisations |
| **Chromium** | Les mesures navigateur récentes portent sur Firefox seul |
| **La pénalité WebAssembly elle-même** | Non rejouée : le natif de comparaison tournait sur une autre machine que le navigateur, ce qui mesurerait la différence de processeurs autant que celle des cibles |
| **Un `k` d'élagage par terrain** | La course est à 91,3 % d'accord contre 98,3 % en contact ; un réglage distinct n'a pas été mesuré |
| **Le 4-ply en qualité** | La profondeur existe et son coût est mesuré (100 à 257 s/décision) ; ce qu'elle vaut ne l'est pas |

## Ce qui est supposé

- **Que l'arbitre de la référence publiée est voisin du nôtre.** L'accord aux trois profondeurs du
  PR est un argument fort, pas une preuve.
- **Que la table d'équité de match Kazaross-XG2 est correcte.** Elle est vérifiée contre le rendu de
  GNU Backgammon, ce qui teste l'accord, pas la vérité.
- **Que les efficacités de videau mesurées se transportent.** Elles sont ajustées sur nos données,
  et rien ne garantit qu'elles vaillent hors du domaine où elles ont été ajustées.

## Les limites de l'artefact publié

- **La table exacte de fin de partie n'est pas incluse** : celle que la recherche consulte pèse
  1,2 Gio. Le moteur retombe donc sur le réseau en fin de partie, ce qui coûte **0,00028 d'équité
  par décision de bearoff** — mesuré, là où GNU Backgammon consulte la sienne et n'y perd rien.
  Le pire cas mesuré vaut 0,0919 sur une seule décision : **c'est la queue, pas la moyenne, qui
  coûte**.
- **Les poids sont en float16 dans la variante légère**, ce qui déplace 0,015 % des décisions —
  mesuré, ~1e-9 d'équité, « 1/100 000 du bruit ».
- **L'élagage est actif par défaut à `k = 12`**, ce qui coûte +0,00023 d'équité par décision. Le
  désactiver rend la recherche d'avant, bit pour bit.

## Les limites des métriques elles-mêmes

- **Un PR mesuré contre GNU Backgammon n'est reproductible qu'à ~±0,005** d'un build à l'autre, à
  version nominale et poids identiques. Mesuré sur deux machines.
- **Les échelles d'équité ne se comparent pas d'un moteur à l'autre.** La nôtre est `2·MWC − 1`,
  celle de gnubg sous un contexte de match est l'EMG. Elles sont affines l'une de l'autre, donc les
  **classements** se comparent et les **magnitudes** non.
- **Chaque arbitre se favorise** par construction. C'est pourquoi deux colonnes sont produites, et
  aucune publiée seule.

## Ce qui a été mesuré à notre désavantage

- **L'avantage du réseau s'annule sous recherche** : +0,00247 d'équité par décision au 0-ply,
  **+0,00007 au 2-ply**. L'information que notre réseau a en plus est précisément celle que deux
  plies de recherche retrouvent tout seuls.
- **La profondeur n'est pas un levier de force** : un ply entier de plus rapporte +0,00022 —
  dans le bruit — pour un coût multiplié par quinze. Mesuré deux fois, avec deux arbitres.
- **Nous restons ~24× à ~56× plus lents que GNU Backgammon par décision**, selon le réglage
  d'élagage.
- **Quatre projections d'optimisation ont été démenties** par la mesure, dont une qui allait dans
  le mauvais sens.

## Les erreurs trouvées, et ce qu'elles disent du dispositif

Elles sont listées parce qu'un dispositif de mesure se juge à ce qu'il attrape.

| Erreur | Comment elle a été trouvée |
|---|---|
| Une campagne de 4,8 jours mesurait un GNU Backgammon estropié | Une signature dans le journal : 84,1 % des paires post-Crawford à un videau impossible |
| Un filtre mal posé rendait le 1-ply identique au 0-ply | Le contrôle bloquant du PR |
| Un artefact publiait une table que le moteur ne charge pas | Le module l'a **refusée** au lieu de l'ignorer |
| Une équité déplacée de 3e-9 par un refactor | Une comparaison bit à bit après réarrangement |
| Un état de match non retourné dans l'analyse de match | Relecture, avant publication |

Dans chaque cas, ce qui a fonctionné est un **refus** ou une **vérification**, jamais une intuition.

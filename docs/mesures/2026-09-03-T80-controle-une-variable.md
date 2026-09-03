# 2026-09-03 — T80, le contrôle à une seule variable : c'est bien l'interférence entre têtes

**Fiche** : T80. **Ce document ferme la question laissée ouverte la veille.**

## La question

Le réseau à quatre sorties de T80 dégradait la colonne cubeless au banc de T78 : pire cas 0,0014
→ 0,0094, et douze décisions au-delà du pire cas de GNU Backgammon (0,0023) là où T78 n'en
laissait aucune. La règle de diagnostic de la fiche nomme ce symptôme **interférence entre
têtes**. Mais deux choses avaient changé, pas une : le réseau avait quatre sorties **et** l'étage
d'affinage par décision de coup n'avait pas tourné, faute de processeurs libres.

Invoquer l'architecture dans ces conditions aurait été l'explication qui arrange. La fiche impose
« une seule chose change à la fois ».

## Le contrôle

Même gabarit, même graine, même budget, le corpus d'un million de décisions de bearoff produit
entre-temps, et **l'étage d'affinage par décision de coup en plus** (8 000 pas). Rien d'autre ne
diffère.

| Réseau | Accord | Perte moyenne | **Pire cas** | Au-delà du repère gnubg |
|---|---|---|---|---|
| T78, une sortie | — | 0,00001 | **0,0014** | **0** |
| T80 sans l'étage | 98,575 % | 0,000012 | **0,00943** | 12 |
| T80 **avec** l'étage | 98,788 % | 0,000011 | **0,00943** | 11 |

**Le pire cas est identique au dix-millième près.** L'étage gagne 0,2 point d'accord et retire une
seule décision sur douze au-delà du repère.

## Le verdict

**L'étage manquant n'expliquait pas la dégradation. La cause est l'interférence entre têtes**, et
c'est maintenant une cause mesurée et non une hypothèse commode.

La suite est celle que la fiche écrit d'avance pour ce symptôme : **têtes séparées, ou pondération
des étages**. Le choix entre les deux se fera par la mesure, pas par principe, et une seule chose
changera à la fois.

## Ce que le contrôle ne remet pas en cause

Le résultat de videau tient, à l'identique : facteur 241 au videau possédé et 1 352 au centré sur
l'échantillon de la fiche, accord 99,8 % et 99,9 %. La preuve d'existence de T80 — un réseau peut
battre Janowski sur une décision de videau — n'est pas touchée par ce diagnostic, qui ne porte que
sur la colonne cubeless.

Le pire cas au videau centré à 20 000 positions reste à 0,0555, au-dessus du seuil de 0,05 fixé
avant la mesure. Ce critère-là reste manqué, de 11 %.

## Ce que cela coûterait de ne pas l'avoir fait

Sans ce contrôle, la fiche aurait pu conclure « c'était l'architecture » ou « il manquait un
étage » avec la même vraisemblance, et T83 aurait branché dans le moteur un réseau dont la queue
est six fois pire que celle de T78 sans savoir pourquoi. Le contrôle a coûté une heure de machine
qui dormait de toute façon.

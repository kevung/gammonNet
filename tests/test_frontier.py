"""La frontière, rendue exécutable — `CONTEXT.md`, `CLAUDE.md`.

*« Ce dépôt évalue une position. Il ne connaît pas ses appelants. »* La règle
existait ; rien ne la vérifiait, et elle s'est érodée jusqu'à ce que le dépôt
nomme des appelants, leur prescrive du travail, et adosse une justification de
licence à l'un d'eux.

## Pourquoi il n'y a AUCUN nom dans ce fichier

Le garde-fou évident serait une liste de noms interdits. Dans un dépôt public,
un tel fichier **dit plus que ce qu'il empêche** : il annonce que ces noms
existent, qu'ils comptent, et qu'on les cache. C'est une divulgation plus forte
que la mention distraite qu'il préviendrait.

Ce qui est vérifié ici est donc une **grammaire**, pas une liste : le dépôt
parle de CIBLES et d'APPELANTS ANONYMES. Une fois cette grammaire tenue, aucun
nom nouveau ne peut entrer — il n'existe plus de phrase pour le porter. On ne
dit plus « ce que X reprend », on dit « ce que la cible WebAssembly expose », et
un nom n'a plus de place syntaxique où se loger.

## Les deux signaux, et les trois que la mesure a écartés

Chaque signal ci-dessous vise **zéro**, et chacun a été compté avant d'être
retenu. Trois candidats ont été écartés parce que la mesure disait qu'ils
n'attrapaient que du légitime :

  * une allowlist d'URL GitHub -- 24 dépôts cités, presque tous la bibliographie
    d'état de l'art de `BRIEF.md` (wildbg, bgsage, KataGo, Stockfish) ;
  * les références d'issue inter-dépôts (`identifiant#1234`) -- un seul site, et
    c'est une issue du standard WebAssembly ;
  * « en aval » et « downstream » adverbiaux -- ils désignent la suite d'un
    CALCUL (« poisons every measurement downstream »), pas une partie. Seul
    l'emploi NOMINAL (« un downstream ») désigne quelqu'un, et lui est vérifié.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Ce que l'on relit : le texte que quelqu'un peut lire, pas les données générées.
SUFFIXES = {".md", ".py", ".c", ".h", ".mjs", ".html"}
NAMES = {"Makefile"}

# 1. LE VOCABULAIRE DE SUBORDINATION. `CONTEXT.md` range ces mots sous _Éviter_ :
#    chacun suppose un lien de subordination que ce dépôt n'a pas à porter. Le
#    mot juste est APPELANT (anonyme par construction) ou CIBLE (à nous).
SUBORDINATION = re.compile(
    r"consommateur|consumer|\b(?:un|une|a|the|le|les|des)\s+downstream\b",
    re.IGNORECASE,
)

# 2. UN FICHIER SOURCE QUI N'EXISTE PAS ICI. Ce dépôt ne produit ni Go ni
#    TypeScript : une mention d'un tel chemin décrit forcément le code de
#    quelqu'un d'autre.
FOREIGN_SOURCE = re.compile(r"[A-Za-z0-9_/.-]+\.(?:go|ts|tsx)(?![A-Za-z0-9])")

# La ligne du glossaire qui NOMME les mots proscrits est la seule exception : un
# glossaire doit pouvoir citer ce qu'il interdit.
GLOSSARY_LINE = "_Éviter_"


def tracked_text_files() -> list[Path]:
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    files = []
    for name in listing:
        if not name:
            continue
        path = ROOT / name
        if path.name == Path(__file__).name:
            continue          # ce fichier cite les motifs qu'il cherche
        if path.suffix in SUFFIXES or path.name in NAMES:
            files.append(path)
    return files


def offences(pattern: re.Pattern[str]) -> list[str]:
    found = []
    for path in tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if GLOSSARY_LINE in line:
                continue
            if pattern.search(line):
                found.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    return found


def test_the_repository_does_not_speak_of_its_callers_as_subordinates():
    """Aucun « consommateur ». Le dépôt a des CIBLES et des APPELANTS anonymes.

    Un appelant nommé n'est jamais seulement nommé : il finit par recevoir des
    ordres. Trois sections « ce que les consommateurs reprennent » avaient fini
    par inventorier les fichiers d'un autre dépôt et prescrire quoi supprimer.
    """
    found = offences(SUBORDINATION)
    assert not found, (
        "vocabulaire de subordination ("
        + str(len(found)) + " site(s)) — dire APPELANT (anonyme) ou CIBLE :\n"
        + "\n".join(found)
    )


def test_no_source_file_this_repository_could_not_have_written():
    """Aucun chemin `.go`, `.ts` ou `.tsx` : ce dépôt n'en produit pas un seul.

    Un tel chemin ne peut désigner que le code de quelqu'un d'autre — et une
    référence qu'aucun test d'ici ne peut vérifier pourrit en silence.
    """
    found = offences(FOREIGN_SOURCE)
    assert not found, (
        "chemin d'un fichier source étranger ("
        + str(len(found)) + " site(s)) :\n" + "\n".join(found)
    )


def test_the_glossary_that_defines_the_rule_exists():
    """`CONTEXT.md` porte les termes que les deux tests ci-dessus supposent."""
    context = ROOT / "CONTEXT.md"
    assert context.is_file(), "CONTEXT.md manque : les tests ci-dessus n'ont plus de définition"
    text = context.read_text(encoding="utf-8")
    for term in ("**Cible**", "**Appelant**", "**Portage**", "**Source**", "**Témoin**"):
        assert term in text, f"{term} absent de CONTEXT.md"

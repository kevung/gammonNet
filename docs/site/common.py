"""Réglages partagés par les deux langues.

Deux projets Sphinx plutôt qu'un seul avec gettext : le contenu est écrit à la
main dans les deux langues, pas traduit mécaniquement, et un catalogue `.po`
ferait croire à une traduction automatique qu'il faudrait maintenir. Ce qui est
partagé — thème, extensions, options — vit ici et n'a qu'une définition.
"""

from __future__ import annotations

project = "gammonNet"
author = "Kevin Unger"
copyright = "2026, Kevin Unger — documentation sous licence MIT"

extensions = ["myst_parser", "sphinx_design"]
myst_enable_extensions = ["colon_fence", "deflist", "attrs_inline"]

templates_path = ["../_templates"]
exclude_patterns = ["_build"]
html_theme = "furo"
html_static_path = ["../_static"]
html_title = "gammonNet"

#: Le pied de page dit ce que la documentation N'EST PAS : une vitrine. Chaque
#: chiffre y renvoie à sa fiche et à sa commande de reproduction.
html_theme_options = {
    "source_repository": "https://github.com/kevung/gammonNet",
    "source_branch": "main",
}

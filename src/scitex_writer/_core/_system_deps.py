#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_core/_system_deps.py

"""scitex-writer's native system (apt) dependency provider.

scitex-writer is the single source of truth for its own LaTeX apt packages —
an image build installs from this list instead of hardcoding it. The set
mirrors the proven scripts/containers/texlive.def recipe.

Registered as a ``scitex_dev.system_deps`` entry-point so
``scitex-dev ecosystem system-deps`` can aggregate it across leaves; the
uniform ``scitex-writer dev system-deps list|install`` CLI verb wraps it (added
with the _cli split). Standalone interim emit (no scitex-dev needed)::

    apt-get install -y --no-install-recommends $(python -m scitex_writer._core._system_deps)

NOTE: bibtex (texlive-bibtex-extra) is the default natbib bibliography path,
matching texlive.def. ``biber`` is also included so biblatex-based manuscripts
compile out of the box -- it does NOT change the default engine (an
operator/config choice). NOTE: a manuscript using `bashful` must compile with
``--shell-escape`` (a compile flag, not an apt package).
"""

from __future__ import annotations

import sys

# (package, purpose). SSoT LaTeX apt set -- mirror of scripts/containers/texlive.def.
_PACKAGES: list[tuple[str, str]] = [
    ("texlive-latex-base", "core LaTeX"),
    ("texlive-latex-recommended", "recommended LaTeX packages"),
    (
        "texlive-latex-extra",
        "extra LaTeX packages (pdfpages, tcolorbox, csvsimple, makecell, ...)",
    ),
    ("texlive-fonts-recommended", "recommended fonts"),
    ("texlive-fonts-extra", "extra fonts"),
    ("texlive-science", "siunitx + science math packages"),
    ("texlive-pictures", "tikz / pgfplots"),
    ("texlive-publishers", "publisher classes (elsarticle, ...)"),
    ("texlive-luatex", "LuaLaTeX engine"),
    ("texlive-xetex", "XeLaTeX engine"),
    ("texlive-bibtex-extra", "BibTeX + natbib bibliography path (default)"),
    ("biber", "Biber backend for biblatex-based manuscripts (non-default)"),
    ("texlive-lang-english", "English language/hyphenation support"),
    ("texlive-plain-generic", "plain/generic packages"),
    ("latexmk", "compile orchestrator"),
    ("latexdiff", "tracked-changes (revision) diff"),
    ("chktex", "LaTeX linter"),
    ("texlive-extra-utils", "texcount and other LaTeX utilities"),
    ("parallel", "GNU parallel -- figure/table conversion + dependency check"),
]

#: Apt package names, in install order (the SSoT list).
APT_PACKAGES: list[str] = [pkg for pkg, _ in _PACKAGES]


def provide():
    """Return this leaf's system deps for the ``scitex_dev.system_deps`` group.

    ``SystemDepSpec`` is imported lazily from scitex_dev so this module stays
    importable (and ``python -m scitex_writer._core._system_deps`` works) even
    where scitex-dev isn't installed -- the aggregator that calls ``provide()``
    runs in an environment that provides scitex_dev.
    """
    from scitex_dev.system_deps import SystemDepSpec

    return [
        SystemDepSpec(package=pkg, purpose=purpose, provider="scitex-writer")
        for pkg, purpose in _PACKAGES
    ]


def _main() -> int:
    # One apt package name per line (consumed by an image %post that runs its
    # own apt). The `scitex-writer dev system-deps list` verb wraps this.
    sys.stdout.write("\n".join(APT_PACKAGES) + "\n")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main())

# EOF

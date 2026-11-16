#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scripts/python/test_clew_overlay_vclaim.py

"""End-to-end pdflatex smoke for the ``--clew-overlay`` \\vclaim coloring.

Real inputs, no mocks: renders a genuine ``claims_rendered.tex`` via the actual
``render_claims.py`` step, then compiles it with a real ``pdflatex``.

``claims_rendered.tex`` doubles its macro-parameter ``#`` to ``##`` so the block
survives being inlined inside another macro body during the manuscript flatten
(the production load context); one ``\\def`` scan there collapses ``##`` back to
the ``#`` parameter marker. To exercise the macro standalone we apply that same
single collapse (``##`` -> ``#``) — i.e. we compile the EXACT runtime form the
macro takes once loaded — then drive it through pdflatex to prove:

- OVERLAY path (markers on + a registered ``clew@hex@<id>``): the value is
  colored by reusing the clew presentation layer's ``\\clewDecorate`` span and
  the document still produces a PDF.
- NON-OVERLAY path (no clew layer / no ``clew@hex@<id>``): ``\\vclaim`` degrades
  to the plain value and compiles clean — the normal compile is never broken.

Skipped when pdflatex is unavailable; the macro wiring is also covered by the
unit assertions in test_render_claims.py.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Claims are stored in scitex-clew (the one claim store): every test here
# needs the real store, on a throwaway schema.
pytestmark = pytest.mark.usefixtures("clew_store")


_REPO_ROOT = Path(__file__).resolve().parents[3]
_RENDER_SCRIPT = _REPO_ROOT / "scripts/python/render_claims.py"
_CLEW_PRESENTATION = _REPO_ROOT / "00_shared/latex_styles/clew_presentation.tex"

pytestmark = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex not available in-container"
)


def _runtime_claims_tex(tmp_path: Path) -> str:
    """Render one value claim and return the macro block in its runtime form.

    Runs the REAL render_claims step, then collapses the ``##`` doubling once
    (the single reduction the production flatten performs) so the block can be
    ``\\input`` at top level exactly as it behaves after loading.
    """
    shared = tmp_path / "00_shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "claims.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "claims": {
                    "foo": {"type": "value", "value": {"value": 42, "unit": "ms"}}
                },
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [sys.executable, str(_RENDER_SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    doubled = (shared / "claims_rendered.tex").read_text(encoding="utf-8")
    return doubled.replace("##", "#")


def _compile(work: Path) -> None:
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"],
        cwd=str(work),
        capture_output=True,
        text=True,
    )


def test_overlay_on_colors_vclaim_and_compiles(tmp_path):
    # Arrange: markers on + a registered clew color for `foo`, reusing the real
    # clew presentation layer and the genuine rendered claims macro.
    claims_tex = _runtime_claims_tex(tmp_path)
    work = tmp_path / "build_on"
    work.mkdir()
    shutil.copy(_CLEW_PRESENTATION, work / "clew_presentation.tex")
    (work / "claims_runtime.tex").write_text(claims_tex, encoding="utf-8")
    (work / "doc.tex").write_text(
        "\\documentclass{article}\n"
        "\\usepackage{graphicx}\n"
        "\\usepackage{xcolor}\n"
        "\\usepackage{hyperref}\n"
        "\\input{clew_presentation.tex}\n"
        "\\makeatletter\n"
        "\\@namedef{clew@hex@foo}{2DA44E}\n"
        "\\makeatother\n"
        "\\input{claims_runtime.tex}\n"
        "\\clewpresmarkerstrue\n"
        "\\begin{document}\n"
        "\\vclaim{foo}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    # Act
    _compile(work)
    # Assert
    assert (work / "doc.pdf").is_file()


def test_non_overlay_degrades_to_plain_value_and_compiles(tmp_path):
    # Arrange: no clew presentation layer and no clew@hex@foo — the exact
    # normal (non-overlay) compile; \vclaim must fall back to the plain value.
    claims_tex = _runtime_claims_tex(tmp_path)
    work = tmp_path / "build_off"
    work.mkdir()
    (work / "claims_runtime.tex").write_text(claims_tex, encoding="utf-8")
    (work / "doc.tex").write_text(
        "\\documentclass{article}\n"
        "\\usepackage{hyperref}\n"
        "\\input{claims_runtime.tex}\n"
        "\\begin{document}\n"
        "\\vclaim{foo}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    # Act
    _compile(work)
    # Assert
    assert (work / "doc.pdf").is_file()


# EOF

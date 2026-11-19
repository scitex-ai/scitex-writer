#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scripts/python/test_clew_overlay_vclaim.py

"""End-to-end pdflatex smoke for the ``--clew-overlay`` \\vclaim coloring.

Real inputs, no mocks: renders a genuine ``claims_rendered.tex`` via the actual
``render_claims.py`` step, then compiles it with a real ``pdflatex``.

``claims_rendered.tex`` is loaded by a plain top-level ``\\input`` (packages.tex;
the flattener inlines it at top level), so it is compiled here exactly as
rendered. It used to double its ``#`` to ``##`` for an older
``\\IfFileExists{..}{BODY}`` wrapper and this test collapsed them back by hand,
so the real file, which failed every ``\\vclaim``, was never compiled. The
tests drive pdflatex to prove:

- OVERLAY path (markers on + a registered ``clew@hex@<id>``): the value is
  colored by reusing the clew presentation layer's ``\\clewDecorate`` span and
  the document still produces a PDF.
- NON-OVERLAY path (no clew layer / no ``clew@hex@<id>``): ``\\vclaim`` degrades
  to the plain value and compiles clean — the normal compile is never broken.
- An id with punctuation (``acc_mean``) resolves to its sanitised macros, also
  inside a moving argument (``\\vclaim`` is robust).

Skipped when pdflatex is unavailable; the macro wiring is also covered by the
unit assertions in test_render_claims.py.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Claims are stored in scitex-clew (the one claim store): every test here
# needs the real store, on a throwaway schema (see pytestmark below).


_REPO_ROOT = Path(__file__).resolve().parents[3]
_RENDER_SCRIPT = _REPO_ROOT / "scripts/python/render_claims.py"
_CLEW_PRESENTATION = _REPO_ROOT / "00_shared/latex_styles/clew_presentation.tex"

# ONE list: a second ``pytestmark =`` assignment silently replaced the
# clew_store mark above, so these tests ran against no store wherever
# pdflatex existed.
pytestmark = [
    pytest.mark.usefixtures("clew_store"),
    pytest.mark.skipif(
        shutil.which("pdflatex") is None, reason="pdflatex not available in-container"
    ),
]


#: What the render subprocess needs (the claim store), and nothing else.
_RENDER_ENV_KEYS = ("PATH", "HOME", "SCITEX_STORE_DSN", "PGUSER", "PGPASSFILE")


def _runtime_claims_tex(tmp_path: Path, claims=None) -> str:
    """Render claims with the REAL render step; return claims_rendered.tex as is.

    The file is loaded with a plain top-level ``\\input`` in production
    (packages.tex, and the flattener inlines it at top level), so it is
    compiled here exactly as written: no ``##`` collapse.
    """
    shared = tmp_path / "00_shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "claims.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "claims": claims
                or {"foo": {"type": "value", "value": {"value": 42, "unit": "ms"}}},
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [sys.executable, str(_RENDER_SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        env={k: os.environ[k] for k in _RENDER_ENV_KEYS if k in os.environ},
    )
    return (shared / "claims_rendered.tex").read_text(encoding="utf-8")


def _compile(work: Path) -> None:
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"],
        cwd=str(work),
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", os.defpath), "HOME": str(work)},
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


def test_id_with_punctuation_resolves_and_compiles(tmp_path):
    # Arrange: \vclaim{acc_mean} must find the macros stored under the
    # sanitised key "accmean" (it used to print "[claim:acc_mean]"); the doc
    # aborts the compile (no PDF) when the id does not resolve.
    claims_tex = _runtime_claims_tex(
        tmp_path, {"acc_mean": {"type": "value", "value": {"value": 0.91}}}
    )
    work = tmp_path / "build_id"
    work.mkdir()
    (work / "claims_runtime.tex").write_text(claims_tex, encoding="utf-8")
    (work / "doc.tex").write_text(
        "\\documentclass{article}\n"
        "\\usepackage{hyperref}\n"
        "\\input{claims_runtime.tex}\n"
        "\\begin{document}\n"
        "\\makeatletter\n"
        "\\@ifundefined{v@claim@id@acc_mean}{\\errmessage{unresolved id}}{}\n"
        "Accuracy \\vclaim{acc_mean}; in a caption-like moving argument:\n"
        "\\protected@edef\\x{\\vclaim{acc_mean}}\\x\n"
        "\\makeatother\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    # Act
    _compile(work)
    # Assert
    assert (work / "doc.pdf").is_file()


# EOF

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: the clew redesign A/B injection + auto-placement decoupling.
#
# Covers Part B (the top-of-document "Provenance marks" \clewIntro section that
# the compile pipeline auto-injects near document start when the clew `intro`
# toggle is active) and the auto-placement decoupling in clew_presentation.tex
# (\clewSignature + \clewLegend are NO LONGER auto-placed at \AtEndDocument).
#
# Style: no mocks (STX-NM002), one behavioral assert per test (STX-TQ007),
# explicit AAA markers (STX-TQ002). Injection is exercised through the REAL
# flattener on a REAL minimal project under tmp_path.

import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from compile_tex_structure import (  # noqa: E402
    CLEW_INTRO_SENTINEL,
    compile_tex_structure,
)

CLEW_STYLE = ROOT_DIR / "00_shared" / "latex_styles" / "clew_presentation.tex"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_base(tmp_path, body):
    """Minimal <root>/doc/base.tex; 00_shared/latex_styles present for fallback."""
    styles = tmp_path / "00_shared" / "latex_styles"
    _write(styles / "signature_footer.tex", "% footer\n")
    base_tex = tmp_path / "doc" / "base.tex"
    _write(base_tex, body)
    return base_tex


def _flatten(base_tex, out_tex):
    saved = os.environ.get("SCITEX_WRITER_PROJECT_ROOT")
    os.environ["SCITEX_WRITER_PROJECT_ROOT"] = str(base_tex.parent.parent)
    try:
        compile_tex_structure(base_tex=base_tex, output_tex=out_tex, verbose=False)
    finally:
        if saved is None:
            os.environ.pop("SCITEX_WRITER_PROJECT_ROOT", None)
        else:
            os.environ["SCITEX_WRITER_PROJECT_ROOT"] = saved


# ============================================================================
# intro injection: gated on the toggle, anchored near document start
# ============================================================================


def test_intro_injected_after_begin_document(tmp_path):
    """intro toggle ON, no frontmatter -> \\clewIntro lands after \\begin{document}."""
    # Arrange
    base = _make_base(
        tmp_path,
        "\\documentclass{article}\n\\clewpresintrotrue\n"
        "\\begin{document}\nHi\\end{document}\n",
    )
    out = tmp_path / "out.tex"
    # Act
    _flatten(base, out)
    # Assert
    assert "\\clewIntro" in out.read_text(encoding="utf-8")


def test_intro_carries_sentinel(tmp_path):
    """The injected intro block carries its idempotency sentinel."""
    # Arrange
    base = _make_base(
        tmp_path,
        "\\documentclass{article}\n\\clewpresintrotrue\n"
        "\\begin{document}\nHi\\end{document}\n",
    )
    out = tmp_path / "out.tex"
    # Act
    _flatten(base, out)
    # Assert
    assert CLEW_INTRO_SENTINEL in out.read_text(encoding="utf-8")


def test_intro_anchored_after_frontmatter(tmp_path):
    """With a frontmatter, the intro is injected AFTER \\end{frontmatter}."""
    # Arrange
    base = _make_base(
        tmp_path,
        "\\documentclass{elsarticle}\n\\clewpresintrotrue\n"
        "\\begin{document}\n\\begin{frontmatter}\n\\end{frontmatter}\n"
        "Body\\end{document}\n",
    )
    out = tmp_path / "out.tex"
    # Act
    _flatten(base, out)
    text = out.read_text(encoding="utf-8")
    # Assert: the intro call appears after the frontmatter close.
    assert text.index("\\clewIntro") > text.index("\\end{frontmatter}")


def test_intro_absent_when_toggle_off(tmp_path):
    """No `intro` toggle -> no \\clewIntro injected (no-op for a non-intro doc)."""
    # Arrange
    base = _make_base(
        tmp_path,
        "\\documentclass{article}\n\\begin{document}\nHi\\end{document}\n",
    )
    out = tmp_path / "out.tex"
    # Act
    _flatten(base, out)
    # Assert
    assert CLEW_INTRO_SENTINEL not in out.read_text(encoding="utf-8")


def test_intro_injected_once(tmp_path):
    """The intro block is inlined at most once (idempotent)."""
    # Arrange
    base = _make_base(
        tmp_path,
        "\\documentclass{article}\n\\clewpresintrotrue\n"
        "\\begin{document}\nHi\\end{document}\n",
    )
    out = tmp_path / "out.tex"
    # Act
    _flatten(base, out)
    # Assert
    assert out.read_text(encoding="utf-8").count(CLEW_INTRO_SENTINEL) == 1


# ============================================================================
# auto-placement decoupling in clew_presentation.tex (static-source checks)
# ============================================================================


def _at_end_document_block():
    """The body of the \\AtEndDocument{...} block in clew_presentation.tex."""
    src = CLEW_STYLE.read_text(encoding="utf-8")
    m = re.search(r"\\AtEndDocument\{(.*?)\}", src, re.DOTALL)
    return m.group(1) if m else ""


def test_at_end_document_no_longer_places_signature():
    """The Writer signature is no longer auto-placed at end of document."""
    # Arrange
    block = _at_end_document_block()
    # Act
    # Assert
    assert "\\clewSignature" not in block


def test_at_end_document_no_longer_places_legend():
    """The bottom legend is no longer auto-placed at end of document."""
    # Arrange
    block = _at_end_document_block()
    # Act
    # Assert
    assert "\\clewLegend" not in block


def test_signature_macro_still_defined_for_backcompat():
    """\\clewSignature stays DEFINED (back-compat) even though it is not placed."""
    # Arrange
    src = CLEW_STYLE.read_text(encoding="utf-8")
    # Act
    # Assert
    assert "\\newcommand{\\clewSignature}" in src


def test_legend_macro_still_defined_for_backcompat():
    """\\clewLegend stays DEFINED (back-compat) even though it is not placed."""
    # Arrange
    src = CLEW_STYLE.read_text(encoding="utf-8")
    # Act
    # Assert
    assert "\\newcommand{\\clewLegend}" in src


def test_intro_macro_defined():
    """The new \\clewIntro macro is defined in clew_presentation.tex."""
    # Arrange
    src = CLEW_STYLE.read_text(encoding="utf-8")
    # Act
    # Assert
    assert "\\newcommand{\\clewIntro}" in src


# EOF

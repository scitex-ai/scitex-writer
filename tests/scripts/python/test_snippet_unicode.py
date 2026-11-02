"""Writer-owned wrappers preserve searchable ligatures without editing full documents."""

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BUILDER = runpy.run_path(str(ROOT / "scripts/python/tex_snippet2full.py"))


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_owned_snippet_selects_outline_fonts_and_unicode_mapping(mode):
    # Arrange
    body = "Finding verified efficient affine workflow office."
    # Act
    document = BUILDER["wrap_body_content"](body, mode)
    # Assert
    assert all(part in document for part in (
        r"\usepackage{lmodern}", r"\input{glyphtounicode}",
        r"\pdfgentounicode=1", body,
    ))


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_complete_document_keeps_author_font_and_mapping_policy(mode):
    # Arrange
    original = "\\documentclass{article}\n\\usepackage{times}\n\\begin{document}Text\\end{document}"
    # Act
    document = BUILDER["inject_color_into_document"](original, mode)
    # Assert
    assert r"\usepackage{times}" in document and "lmodern" not in document and "glyphtounicode" not in document


def test_supported_native_installer_declares_outline_font_dependency():
    # Arrange
    packages = (ROOT / "scripts/installation/requirements/system-debian.txt").read_text().splitlines()
    # Act
    required = "lmodern" in packages
    # Assert
    assert required

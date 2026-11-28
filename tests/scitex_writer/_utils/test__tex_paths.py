#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_utils/test__tex_paths.py

"""Generated .tex names files relative to the project root, never absolutely."""

import pytest
from PIL import Image

from scitex_writer._mcp.handlers import _figures_tex
from scitex_writer._mcp.handlers._tables_pipeline import gather_table_tex_files
from scitex_writer._utils._tex_paths import tex_path


class TestTexPath:
    def test_inside_root_is_dot_relative(self, tmp_path):
        # Arrange
        path = tmp_path / "01_manuscript" / "fig.jpg"
        # Act
        out = tex_path(path, tmp_path)
        # Assert
        assert out == "./01_manuscript/fig.jpg"

    def test_outside_root_is_unchanged(self, tmp_path):
        # Arrange
        root = tmp_path / "paper"
        root.mkdir()
        path = tmp_path / "other" / "fig.jpg"
        # Act
        out = tex_path(path, root)
        # Assert
        assert out == str(path)

    def test_no_root_is_unchanged(self, tmp_path):
        # Arrange
        path = tmp_path / "fig.jpg"
        # Act
        out = tex_path(path, None)
        # Assert
        assert out == str(path)

    def test_symlinked_root_resolves(self, tmp_path):
        # Arrange
        real = tmp_path / "real"
        real.mkdir()
        alias = tmp_path / "alias"
        alias.symlink_to(real)
        # Act
        out = tex_path(real / "a.tex", alias)
        # Assert
        assert out == "./a.tex"


@pytest.fixture
def figure_final(tmp_path):
    """FINAL.tex of one real figure, gathered with tex_root = the project."""
    cam = tmp_path / "01_manuscript/contents/figures/caption_and_media"
    jpg_dir = cam / "jpg_for_compilation"
    compiled = tmp_path / "01_manuscript/contents/figures/compiled"
    for directory in (cam, jpg_dir, compiled):
        directory.mkdir(parents=True, exist_ok=True)
    (cam / "01_overview.tex").write_text("\\caption{X}\n", encoding="utf-8")
    Image.new("RGB", (40, 30), (200, 30, 30)).save(jpg_dir / "01_overview.jpg")
    _figures_tex.compile_legends(cam, compiled)
    final = compiled / "FINAL.tex"
    _figures_tex.compile_figure_tex_files(
        cam, jpg_dir, compiled, final, tex_root=tmp_path
    )
    return tmp_path, final.read_text()


class TestFigureFinal:
    def test_includegraphics_names_the_image_relative_to_the_project(
        self, figure_final
    ):
        # Arrange
        _, text = figure_final
        # Act
        expected = (
            "{./01_manuscript/contents/figures/caption_and_media/"
            "jpg_for_compilation/01_overview.jpg}"
        )
        # Assert
        assert expected in text

    def test_final_tex_carries_no_checkout_path(self, figure_final):
        # Arrange
        root, text = figure_final
        # Act
        leaked = str(root) in text
        # Assert
        assert leaked is False


class TestTableFinal:
    def test_fallback_header_input_is_project_relative(self, tmp_path):
        # Arrange
        compiled = tmp_path / "01_manuscript/contents/tables/compiled"
        compiled.mkdir(parents=True)
        final = compiled / "FINAL.tex"
        # Act
        gather_table_tex_files(compiled, final, tex_root=tmp_path)
        # Assert
        assert (
            "\\input{./01_manuscript/contents/tables/compiled/00_Tables_Header.tex}"
            in final.read_text()
        )

    def test_real_table_input_is_project_relative(self, tmp_path):
        # Arrange
        compiled = tmp_path / "01_manuscript/contents/tables/compiled"
        compiled.mkdir(parents=True)
        (compiled / "01_scores.tex").write_text("TABLE\n", encoding="utf-8")
        final = compiled / "FINAL.tex"
        # Act
        gather_table_tex_files(compiled, final, tex_root=tmp_path)
        # Assert
        assert (
            "\\input{./01_manuscript/contents/tables/compiled/01_scores.tex}"
            in final.read_text()
        )


# EOF

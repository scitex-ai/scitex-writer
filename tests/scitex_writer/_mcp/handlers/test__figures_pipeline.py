#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_mcp/handlers/test__figures_pipeline.py

r"""Tests for the pure-Python figure pipeline (port of process_figures.sh).

Real inputs throughout -- real PNG/TIFF images under ``tmp_path``, the real config
the shell read via ``yq``, and (in the smoke tests) a real ``pdflatex`` compile of
the generated float. No mocks, no monkeypatch.

The compile tests are the whole point: the port is only correct if what it writes
actually typesets, with the real JPG it produced actually embedded.
"""

import shutil
import subprocess

import pytest
from PIL import Image

from scitex_writer._mcp.handlers import _figures_pipeline

_CONFIG = (
    "figures:\n"
    "  max_height_frac: 0.78\n"
    '  dir: "./01_manuscript/contents/figures"\n'
    '  caption_media_dir: "./01_manuscript/contents/figures/caption_and_media"\n'
    "  jpg_dir: "
    '"./01_manuscript/contents/figures/caption_and_media/jpg_for_compilation"\n'
    '  compiled_dir: "./01_manuscript/contents/figures/compiled"\n'
    '  compiled_file: "./01_manuscript/contents/figures/compiled/FINAL.tex"\n'
)

_CAPTION = "\\caption{\\textbf{Overview.}\\\\ The pipeline end to end.}\n"

# A minimal preamble carrying every package the generated float uses.
_PREAMBLE = (
    "\\documentclass{article}\n"
    "\\usepackage{graphicx}\n"
    "\\usepackage{caption}\n"
    "\\usepackage{hyperref}\n"
)


def _png(path, size=(120, 90), color=(30, 90, 200)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "PNG")
    return path


def _seed_project(tmp_path, with_media=True, caption=None):
    """Seed a project with one PNG figure; return (project, caption_media_dir)."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "config_manuscript.yaml").write_text(_CONFIG, encoding="utf-8")
    cam = tmp_path / "01_manuscript/contents/figures/caption_and_media"
    cam.mkdir(parents=True)
    if with_media:
        _png(cam / "01_overview.png")
    if caption is not None:
        (cam / "01_overview.tex").write_text(caption, encoding="utf-8")
    return tmp_path, cam


def _compiled_dir(project):
    return project / "01_manuscript/contents/figures/compiled"


def _jpg_dir(project):
    return (
        project / "01_manuscript/contents/figures/caption_and_media/jpg_for_compilation"
    )


def _compile(work, tex_body, project):
    """Write and compile a minimal document; return the expected PDF path.

    Runs from the PROJECT ROOT, as the engines do: the generated floats name
    their images relative to it, never by the checkout's absolute path."""
    work.mkdir(parents=True, exist_ok=True)
    (work / "doc.tex").write_text(
        _PREAMBLE + "\\begin{document}\n" + tex_body + "\n\\end{document}\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={work}",
            str(work / "doc.tex"),
        ],
        cwd=str(project),
        capture_output=True,
        text=True,
    )
    return work / "doc.pdf"


class TestPipelineErrors:
    def test_invalid_doc_type_returns_actionable_error(self):
        # Arrange
        bad_doc_type = "poster"
        # Act
        result = _figures_pipeline.process(".", bad_doc_type)
        # Assert
        assert result["success"] is False and "poster" in result["error"]

    def test_missing_project_dir_returns_error_hint(self, tmp_path):
        # Arrange
        absent = tmp_path / "nope"
        # Act
        result = _figures_pipeline.process(str(absent), "manuscript")
        # Assert
        assert result["success"] is False and "not found" in result["error"]

    def test_missing_config_returns_error_hint(self, tmp_path):
        # Arrange
        (tmp_path / "01_manuscript").mkdir()
        # Act
        result = _figures_pipeline.process(str(tmp_path), "manuscript")
        # Assert
        assert result["success"] is False and "Config not found" in result["error"]

    def test_escaping_config_path_is_refused(self, tmp_path):
        # Arrange: a figures.* path that climbs out of the project must not be
        # written to -- the pipeline deletes and rewrites whole directories.
        project = tmp_path / "proj"
        (project / "config").mkdir(parents=True)
        (project / "config/config_manuscript.yaml").write_text(
            _CONFIG.replace('"./01_manuscript', '"../escaped/01_manuscript'),
            encoding="utf-8",
        )
        # Act
        result = _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["success"] is False and "OUTSIDE" in result["error"]


class TestNoFigsMode:
    def test_no_figs_skips_image_work(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        # Act
        result = _figures_pipeline.process(str(project), "manuscript", no_figs=True)
        # Assert
        assert result["skipped"] is True and result["converted"] == 0

    def test_no_figs_disables_figures(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        # Act
        result = _figures_pipeline.process(str(project), "manuscript", no_figs=True)
        # Assert
        assert result["figures_enabled"] is False


class TestFullRun:
    def test_png_source_reaches_the_compilation_dir_as_jpg(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        # Act
        _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert (_jpg_dir(project) / "01_overview.jpg").exists()

    def test_default_caption_is_created(self, tmp_path):
        # Arrange
        project, cam = _seed_project(tmp_path)
        # Act
        result = _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["captions_created"] == 1 and (cam / "01_overview.tex").exists()

    def test_figure_is_compiled_and_reported(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path, caption=_CAPTION)
        # Act
        result = _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["figures_compiled"] == 1 and result["figures_enabled"] is True

    def test_uppercase_panel_id_is_lowercased(self, tmp_path):
        # Arrange
        project, cam = _seed_project(tmp_path, with_media=False)
        _png(cam / "01A_left.png")
        # Act
        result = _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["renamed_panels"] == 1 and (cam / "01a_left.png").exists()

    def test_stray_panel_caption_is_removed(self, tmp_path):
        # Arrange
        project, cam = _seed_project(tmp_path)
        (cam / "01a_left.tex").write_text("\\caption{Panel}", encoding="utf-8")
        # Act
        result = _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["panel_captions_removed"] == 1

    def test_panels_are_composed_into_one_figure(self, tmp_path):
        # Arrange: two panels, no main media -- the shell shipped panel *a* alone.
        project, cam = _seed_project(tmp_path, with_media=False, caption=_CAPTION)
        _png(cam / "01a_left.png")
        _png(cam / "01b_right.png", color=(200, 30, 30))
        # Act
        result = _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["composed"] == 1 and (_jpg_dir(project) / "01.jpg").exists()

    def test_composed_figure_is_wider_than_a_panel(self, tmp_path):
        # Arrange
        project, cam = _seed_project(tmp_path, with_media=False, caption=_CAPTION)
        _png(cam / "01a_left.png")
        _png(cam / "01b_right.png", color=(200, 30, 30))
        # Act
        _figures_pipeline.process(str(project), "manuscript")
        # Assert
        with Image.open(_jpg_dir(project) / "01.jpg") as image:
            assert image.width == 260

    def test_declared_figure_without_media_gets_a_placeholder(self, tmp_path):
        # Arrange: the draft opt-in path (media gate warn/off).
        project, _ = _seed_project(tmp_path, with_media=False, caption=_CAPTION)
        # Act
        result = _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["placeholders_created"] == 1

    def test_tiff_source_walks_the_whole_cascade(self, tmp_path):
        # Arrange
        project, cam = _seed_project(tmp_path, with_media=False, caption=_CAPTION)
        Image.new("RGB", (60, 40), (0, 120, 0)).save(cam / "01_overview.tif", "TIFF")
        # Act
        _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert (_jpg_dir(project) / "01_overview.jpg").exists()

    def test_crop_trims_the_compilation_jpg(self, tmp_path):
        # Arrange: the shell's crop was a silent no-op without ImageMagick.
        project, cam = _seed_project(tmp_path, with_media=False, caption=_CAPTION)
        canvas = Image.new("RGB", (100, 100), (255, 255, 255))
        canvas.paste(Image.new("RGB", (20, 20), (255, 0, 0)), (40, 40))
        canvas.save(cam / "01_overview.png", "PNG")
        # Act
        result = _figures_pipeline.process(str(project), "manuscript", crop=True)
        # Assert
        assert result["cropped"] == 1

    def test_no_figures_emits_fallback_header(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path, with_media=False)
        # Act
        result = _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["fallback_header"] is True and result["figures_compiled"] == 0

    def test_orphan_compilation_jpg_is_surfaced_as_a_warning(self, tmp_path):
        # Arrange: a user-placed JPG with no caption_and_media source.
        project, _ = _seed_project(tmp_path, with_media=False)
        jpg_dir = _jpg_dir(project)
        jpg_dir.mkdir(parents=True)
        Image.new("RGB", (20, 20), (9, 9, 9)).save(jpg_dir / "07_handmade.jpg", "JPEG")
        # Act
        result = _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert any("07_handmade.jpg" in w for w in result["warnings"])

    def test_stale_compiled_tex_is_cleared(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path, caption=_CAPTION)
        compiled = _compiled_dir(project)
        compiled.mkdir(parents=True)
        stale = compiled / "99_stale.tex"
        stale.write_text("stale", encoding="utf-8")
        # Act
        _figures_pipeline.process(str(project), "manuscript")
        # Assert
        assert not stale.exists()


@pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex not available in-container"
)
class TestPdflatexSmoke:
    def test_generated_placeable_float_compiles_to_pdf(self, tmp_path):
        # Arrange: real pipeline output (float + the JPG it produced), real pdflatex.
        project, _ = _seed_project(tmp_path, caption=_CAPTION)
        _figures_pipeline.process(str(project), "manuscript")
        placeable = (_compiled_dir(project) / "_placeable/01.tex").read_text()
        # Act
        pdf = _compile(tmp_path / "build", placeable, project)
        # Assert
        assert pdf.is_file()

    def test_gathered_final_tex_compiles_to_pdf(self, tmp_path):
        # Arrange: the file the manuscript actually inputs -- exercises the guarded
        # \ifcsname block and the \pdfbookmark end to end.
        project, _ = _seed_project(tmp_path, caption=_CAPTION)
        _figures_pipeline.process(str(project), "manuscript")
        final = _compiled_dir(project) / "FINAL.tex"
        # Act
        pdf = _compile(tmp_path / "build_final", f"\\input{{{final}}}", project)
        # Assert
        assert pdf.is_file()

    def test_composed_panel_figure_compiles_to_pdf(self, tmp_path):
        # Arrange: the tiled composite must be a real, embeddable JPG.
        project, cam = _seed_project(tmp_path, with_media=False, caption=_CAPTION)
        _png(cam / "01a_left.png")
        _png(cam / "01b_right.png", color=(200, 30, 30))
        _figures_pipeline.process(str(project), "manuscript")
        final = _compiled_dir(project) / "FINAL.tex"
        # Act
        pdf = _compile(tmp_path / "build_panels", f"\\input{{{final}}}", project)
        # Assert
        assert pdf.is_file()

    def test_caption_footnote_figure_compiles_to_pdf(self, tmp_path):
        # Arrange: a \footnote inside a float is FATAL; the \footnotemark +
        # \footnotetext split this port emits must typeset.
        project, _ = _seed_project(
            tmp_path,
            caption="\\caption{\\textbf{Overview.}\\\\ L.\\captionfootnote{Funded.}}\n",
        )
        _figures_pipeline.process(str(project), "manuscript")
        final = _compiled_dir(project) / "FINAL.tex"
        # Act
        pdf = _compile(tmp_path / "build_footnote", f"\\input{{{final}}}", project)
        # Assert
        assert pdf.is_file()

    def test_empty_manuscript_final_tex_compiles_to_pdf(self, tmp_path):
        # Arrange: the comment-only fallback header must still typeset (and emit
        # no stray figure).
        project, _ = _seed_project(tmp_path, with_media=False)
        _figures_pipeline.process(str(project), "manuscript")
        final = _compiled_dir(project) / "FINAL.tex"
        # Act
        pdf = _compile(tmp_path / "build_empty", f"\\input{{{final}}}", project)
        # Assert
        assert pdf.is_file()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))

# EOF

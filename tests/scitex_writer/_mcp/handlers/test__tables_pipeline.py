#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_mcp/handlers/test__tables_pipeline.py

r"""Tests for the pure-Python table pipeline (port of process_tables.sh).

Real inputs throughout -- real CSV/XLSX files under ``tmp_path``, the real
config the shell read, and (in the smoke test) a real ``pdflatex`` compile of the
generated table. No mocks.

The no-tables cases are the regression guard for card
writer-stray-table-zero-artifact: the fallback header must emit NO table float.
"""

import shutil
import subprocess

import pytest

from scitex_writer._mcp.handlers import _tables_pipeline

_CONFIG = (
    "tables:\n"
    '  dir: "./01_manuscript/contents/tables"\n'
    '  caption_media_dir: "./01_manuscript/contents/tables/caption_and_media"\n'
    '  compiled_dir: "./01_manuscript/contents/tables/compiled"\n'
    '  compiled_file: "./01_manuscript/contents/tables/compiled/FINAL.tex"\n'
)

_CSV = "patient,seizure_count,score\nP1,288,0.333\nP2,12,0.35\n"

# A minimal preamble carrying every package/color the generated float uses.
_PREAMBLE = (
    "\\documentclass{article}\n"
    "\\usepackage{graphicx}\n"
    "\\usepackage{booktabs}\n"
    "\\usepackage[table]{xcolor}\n"
    "\\usepackage{caption}\n"
    "\\usepackage{hyperref}\n"
    "\\definecolor{lightgray}{gray}{0.95}\n"
)


def _seed_project(tmp_path, csv_text=_CSV, caption=None):
    """Seed a project with one CSV table; return (project, caption_media_dir)."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "config_manuscript.yaml").write_text(_CONFIG, encoding="utf-8")
    cam = tmp_path / "01_manuscript/contents/tables/caption_and_media"
    cam.mkdir(parents=True)
    if csv_text is not None:
        (cam / "01_seizure_count.csv").write_text(csv_text, encoding="utf-8")
    if caption is not None:
        (cam / "01_seizure_count.tex").write_text(caption, encoding="utf-8")
    return tmp_path, cam


def _compiled_dir(project):
    return project / "01_manuscript/contents/tables/compiled"


class TestPipelineErrors:
    def test_invalid_doc_type_returns_actionable_error(self):
        # Arrange
        bad_doc_type = "poster"
        # Act
        result = _tables_pipeline.process(".", bad_doc_type)
        # Assert
        assert result["success"] is False and "poster" in result["error"]

    def test_missing_project_dir_returns_error_hint(self, tmp_path):
        # Arrange
        absent = tmp_path / "nope"
        # Act
        result = _tables_pipeline.process(str(absent), "manuscript")
        # Assert
        assert result["success"] is False and "not found" in result["error"]

    def test_missing_config_returns_error_hint(self, tmp_path):
        # Arrange
        (tmp_path / "01_manuscript").mkdir()
        # Act
        result = _tables_pipeline.process(str(tmp_path), "manuscript")
        # Assert
        assert result["success"] is False and "Config not found" in result["error"]

    def test_no_tables_flag_skips_processing(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        # Act
        result = _tables_pipeline.process(str(project), "manuscript", no_tables=True)
        # Assert
        assert result["skipped"] is True and result["tables_compiled"] == 0


class TestCaptionStage:
    def test_default_caption_created_for_uncaptioned_table(self, tmp_path):
        # Arrange
        project, cam = _seed_project(tmp_path)
        # Act
        result = _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert (
            result["captions_created"] == 1 and (cam / "01_seizure_count.tex").exists()
        )

    def test_default_caption_carries_edit_hint(self, tmp_path):
        # Arrange
        project, cam = _seed_project(tmp_path)
        # Act
        _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert "TABLE TITLE HERE" in (cam / "01_seizure_count.tex").read_text()

    def test_existing_caption_is_not_overwritten(self, tmp_path):
        # Arrange
        authored = "\\caption{\\textbf{Mine}\\\\ Authored.}\n"
        project, cam = _seed_project(tmp_path, caption=authored)
        # Act
        result = _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert (
            result["captions_created"] == 0
            and (cam / "01_seizure_count.tex").read_text() == authored
        )


class TestXlsxStage:
    def test_excel_source_is_converted_to_csv(self, tmp_path):
        # Arrange
        import pandas as pd

        project, cam = _seed_project(tmp_path, csv_text=None)
        pd.DataFrame({"patient": ["P1"], "count": [3]}).to_excel(
            cam / "02_from_excel.xlsx", index=False
        )
        # Act
        result = _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["xlsx_converted"] == 1 and (cam / "02_from_excel.csv").exists()

    def test_excel_derived_table_is_compiled(self, tmp_path):
        # Arrange
        import pandas as pd

        project, cam = _seed_project(tmp_path, csv_text=None)
        pd.DataFrame({"patient": ["P1"], "count": [3]}).to_excel(
            cam / "02_from_excel.xlsx", index=False
        )
        # Act
        _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert (_compiled_dir(project) / "02_from_excel.tex").exists()


class TestRenderStage:
    def test_csv_is_rendered_to_compiled_tex(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        # Act
        result = _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert (
            result["tables_compiled"] == 1
            and (_compiled_dir(project) / "01_seizure_count.tex").exists()
        )

    def test_verbatim_math_cell_survives_pipeline(self, tmp_path):
        # Arrange
        project, _ = _seed_project(
            tmp_path, csv_text="metric,value\nsignificance,$p<0.001$\n"
        )
        # Act
        _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert (
            "$p<0.001$" in (_compiled_dir(project) / "01_seizure_count.tex").read_text()
        )

    def test_stale_compiled_tex_is_cleared(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        compiled = _compiled_dir(project)
        compiled.mkdir(parents=True)
        stale = compiled / "99_stale.tex"
        stale.write_text("stale", encoding="utf-8")
        # Act
        _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert not stale.exists()

    def test_per_table_outcome_reports_shape(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        # Act
        result = _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["tables"][0]["rows"] == 2 and result["tables"][0]["columns"] == 3


class TestGatherStage:
    def test_final_tex_guards_inline_placed_table(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        # Act
        _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert (
            "\\ifcsname scitextabplaced@01\\endcsname"
            in (_compiled_dir(project) / "FINAL.tex").read_text()
        )

    def test_placeable_copy_is_written_by_number(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        # Act
        _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert (_compiled_dir(project) / "_placeable/01.tex").exists()

    def test_no_tables_emits_fallback_header(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path, csv_text=None)
        # Act
        result = _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["fallback_header"] is True and result["tables_compiled"] == 0

    def test_fallback_header_emits_no_table_float(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path, csv_text=None)
        # Act
        _tables_pipeline.process(str(project), "manuscript")
        header = (_compiled_dir(project) / "00_Tables_Header.tex").read_text()
        active = "\n".join(
            line for line in header.splitlines() if not line.lstrip().startswith("%")
        )
        # Assert
        assert "\\begin{table}" not in active

    def test_fallback_header_emits_no_zero_label(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path, csv_text=None)
        # Act
        _tables_pipeline.process(str(project), "manuscript")
        header = (_compiled_dir(project) / "00_Tables_Header.tex").read_text()
        active = "\n".join(
            line for line in header.splitlines() if not line.lstrip().startswith("%")
        )
        # Assert
        assert "\\label{tab:" not in active

    def test_real_table_replaces_fallback_header(self, tmp_path):
        # Arrange
        project, _ = _seed_project(tmp_path)
        # Act
        _tables_pipeline.process(str(project), "manuscript")
        # Assert
        assert not (_compiled_dir(project) / "00_Tables_Header.tex").exists()


@pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex not available in-container"
)
class TestPdflatexSmoke:
    def test_generated_table_compiles_to_pdf(self, tmp_path):
        # Arrange: real pipeline output, real pdflatex -- the port is only correct
        # if what it writes actually typesets.
        project, _ = _seed_project(
            tmp_path,
            csv_text="model,$R^2$,p\nlinear,0.333,$p<0.001$\nridge,0.35,$p=0.02$\n",
        )
        _tables_pipeline.process(str(project), "manuscript")
        work = tmp_path / "build"
        work.mkdir()
        table = (_compiled_dir(project) / "01_seizure_count.tex").read_text()
        (work / "doc.tex").write_text(
            _PREAMBLE + "\\begin{document}\n" + table + "\n\\end{document}\n",
            encoding="utf-8",
        )
        # Act: from the project root, as the engines run -- FINAL.tex names its
        # inputs relative to it, never by the checkout's absolute path.
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
        # Assert
        assert (work / "doc.pdf").is_file()

    def test_gathered_final_tex_compiles_to_pdf(self, tmp_path):
        # Arrange: compile the gathered FINAL.tex (the file the manuscript inputs),
        # exercising the guarded \input + \pdfbookmark path end to end.
        project, _ = _seed_project(tmp_path)
        _tables_pipeline.process(str(project), "manuscript")
        work = tmp_path / "build_final"
        work.mkdir()
        final = _compiled_dir(project) / "FINAL.tex"
        (work / "doc.tex").write_text(
            _PREAMBLE
            + "\\begin{document}\n"
            + f"\\input{{{final}}}\n"
            + "\\end{document}\n",
            encoding="utf-8",
        )
        # Act: from the project root, as the engines run -- FINAL.tex names its
        # inputs relative to it, never by the checkout's absolute path.
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
        # Assert
        assert (work / "doc.pdf").is_file()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))

# EOF

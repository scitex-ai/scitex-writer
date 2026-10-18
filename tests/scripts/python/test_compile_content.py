#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-02-08
# File: tests/python/test_compile_content.py

"""Tests for scitex_writer compile.content functionality."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


class TestContentModule:
    """Test content module can be imported."""

    def test_content_import_from_compile_api(self):
        """Test that compile_content is importable from _compile."""
        # Arrange
        # Act
        from scitex_writer._compile.content import compile_content

        # Assert
        assert callable(compile_content)

    def test_content_import_from_mcp_wrapper(self):
        """Test that _mcp.content thin wrapper works."""
        # Arrange
        # Act
        from scitex_writer._mcp.content import compile_content

        # Assert
        assert callable(compile_content)

    def test_content_via_compile_module(self):
        """Test that content is accessible via compile module."""
        # Arrange
        # Act
        from scitex_writer import compile

        # Assert
        assert callable(compile.content)


class TestDocumentBuilder:
    """Test tex_snippet2full.py script functions."""

    @pytest.fixture
    def scripts_dir(self):
        """Get the project's `scripts/` directory.

        Walks up to the directory containing `pyproject.toml` so the lookup
        survives test-tree depth changes.
        """
        p = Path(__file__).resolve()
        for parent in [p, *p.parents]:
            if (parent / "pyproject.toml").is_file():
                return parent / "scripts"
        raise RuntimeError(f"Could not find pyproject.toml from {__file__}")

    def test_document_builder_exists(self, scripts_dir):
        """Test that the document builder script exists."""
        # Arrange
        # Act
        builder = scripts_dir / "python" / "tex_snippet2full.py"
        # Assert
        assert builder.exists()

    def test_shell_script_exists(self, scripts_dir):
        """Test that the compile shell script exists."""
        # Arrange
        # Act
        compiler = scripts_dir / "shell" / "compile_content.sh"
        # Assert
        assert compiler.exists()

    def test_document_builder_light_mode_result_returncode_equals_n_0(
        self, scripts_dir, tmp_path
    ):
        # Arrange
        builder = scripts_dir / "python" / "tex_snippet2full.py"
        body_file = tmp_path / "body.tex"
        body_file.write_text(r"\section{Test}" + "\n\nHello World\n")
        output_file = tmp_path / "output.tex"
        # Act
        result = subprocess.run(
            [
                sys.executable,
                str(builder),
                "--body-file",
                str(body_file),
                "--output",
                str(output_file),
                "--color-mode",
                "light",
            ],
            capture_output=True,
            text=True,
        )
        # Act
        # Assert
        assert result.returncode == 0

    def test_document_builder_light_mode_documentclass_in_content_and_begin_document_in_content_and_h(
        self, scripts_dir, tmp_path
    ):
        # Arrange
        builder = scripts_dir / "python" / "tex_snippet2full.py"
        body_file = tmp_path / "body.tex"
        body_file.write_text(r"\section{Test}" + "\n\nHello World\n")
        output_file = tmp_path / "output.tex"
        result = subprocess.run(
            [
                sys.executable,
                str(builder),
                "--body-file",
                str(body_file),
                "--output",
                str(output_file),
                "--color-mode",
                "light",
            ],
            capture_output=True,
            text=True,
        )
        # Act
        content = output_file.read_text()
        # Act
        # Assert
        assert (
            ("\\documentclass" in content)
            and ("\\begin{document}" in content)
            and ("Hello World" in content)
            and ("MonacoBg" not in content)
        )

    def test_document_builder_dark_mode_result_returncode_equals_n_0(
        self, scripts_dir, tmp_path
    ):
        # Arrange
        builder = scripts_dir / "python" / "tex_snippet2full.py"
        body_file = tmp_path / "body.tex"
        body_file.write_text("Dark mode test content\n")
        output_file = tmp_path / "output.tex"
        # Act
        result = subprocess.run(
            [
                sys.executable,
                str(builder),
                "--body-file",
                str(body_file),
                "--output",
                str(output_file),
                "--color-mode",
                "dark",
            ],
            capture_output=True,
            text=True,
        )
        # Act
        # Assert
        assert result.returncode == 0

    def test_document_builder_dark_mode_monacobg_in_content_and_1e1e1e_in_content_and_monacofg_in_co(
        self, scripts_dir, tmp_path
    ):
        # Arrange
        builder = scripts_dir / "python" / "tex_snippet2full.py"
        body_file = tmp_path / "body.tex"
        body_file.write_text("Dark mode test content\n")
        output_file = tmp_path / "output.tex"
        result = subprocess.run(
            [
                sys.executable,
                str(builder),
                "--body-file",
                str(body_file),
                "--output",
                str(output_file),
                "--color-mode",
                "dark",
            ],
            capture_output=True,
            text=True,
        )
        # Act
        content = output_file.read_text()
        # Act
        # Assert
        assert (
            ("MonacoBg" in content)
            and ("1E1E1E" in content)
            and ("MonacoFg" in content)
            and ("D4D4D4" in content)
            and ("\\pagecolor{MonacoBg}" in content)
            and ("\\color{MonacoFg}" in content)
        )

    def test_document_builder_complete_document_result_returncode_equals_n_0(
        self, scripts_dir, tmp_path
    ):
        # Arrange
        builder = scripts_dir / "python" / "tex_snippet2full.py"
        body_file = tmp_path / "body.tex"
        body_file.write_text(
            "\\documentclass{article}\n\\begin{document}\nComplete doc\n\\end{document}\n"
        )
        output_file = tmp_path / "output.tex"
        # Act
        result = subprocess.run(
            [
                sys.executable,
                str(builder),
                "--body-file",
                str(body_file),
                "--output",
                str(output_file),
                "--color-mode",
                "dark",
                "--complete-document",
            ],
            capture_output=True,
            text=True,
        )
        # Act
        # Assert
        assert result.returncode == 0

    def test_document_builder_complete_document_monaco_pos_begin_pos(
        self, scripts_dir, tmp_path
    ):
        # Arrange
        builder = scripts_dir / "python" / "tex_snippet2full.py"
        body_file = tmp_path / "body.tex"
        body_file.write_text(
            "\\documentclass{article}\n\\begin{document}\nComplete doc\n\\end{document}\n"
        )
        output_file = tmp_path / "output.tex"
        result = subprocess.run(
            [
                sys.executable,
                str(builder),
                "--body-file",
                str(body_file),
                "--output",
                str(output_file),
                "--color-mode",
                "dark",
                "--complete-document",
            ],
            capture_output=True,
            text=True,
        )
        content = output_file.read_text()
        # Should inject after \begin{document}
        begin_pos = content.find("\\begin{document}")
        # Act
        monaco_pos = content.find("MonacoBg")
        # Act
        # Assert
        assert monaco_pos > begin_pos


def _has_latex_package(sty: str) -> bool:
    """True iff kpsewhich resolves the .sty (host TeX set varies by runner)."""
    try:
        proc = subprocess.run(
            ["kpsewhich", sty], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


_REQUIRES_LATEXMK = pytest.mark.skipif(
    shutil.which("latexmk") is None or not _has_latex_package("pagecolor.sty"),
    reason="latexmk or the pagecolor.sty TeX package not available",
)


def _cleanup_temp_dir(result):
    # `result` is a CompilationResult dataclass (G1 unification,
    # 2026-06-10) — drop the legacy `.get("temp_dir")` dict access in
    # favour of attribute access. CompilationResult.temp_dir is
    # Optional[Path]; None when the compile path is not the preview
    # path (e.g. manuscript / supplementary / revision compiles build
    # in-place, no scratch dir to clean up).
    temp = getattr(result, "temp_dir", None)
    if temp is not None:
        temp_dir = Path(temp)
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


class TestContentCompilation:
    """Test content compilation (requires latexmk)."""

    @_REQUIRES_LATEXMK
    def test_compile_simple_content_succeeds(self):
        # Arrange
        from scitex_writer import compile

        content = (
            r"\documentclass{article}"
            "\n"
            r"\begin{document}"
            "\nHello, World!\n"
            r"\end{document}"
            "\n"
        )
        # Act
        result = compile.content(content, name="test_simple")
        _cleanup_temp_dir(result)
        # Assert
        assert result.success is True

    @_REQUIRES_LATEXMK
    def test_compile_simple_content_writes_pdf_on_disk(self):
        # Arrange
        from scitex_writer import compile

        content = (
            r"\documentclass{article}"
            "\n"
            r"\begin{document}"
            "\nHello, World!\n"
            r"\end{document}"
            "\n"
        )
        # Act
        result = compile.content(content, name="test_simple")
        pdf_exists = (
            result.output_pdf is not None and Path(result.output_pdf).exists()
        )
        _cleanup_temp_dir(result)
        # Assert
        assert pdf_exists is True

    @_REQUIRES_LATEXMK
    def test_compile_body_only_content_succeeds(self):
        # Arrange
        from scitex_writer import compile

        content = "\n" r"\section{Introduction}" "\n\nThis is the introduction.\n"
        # Act
        result = compile.content(content, name="test_body")
        _cleanup_temp_dir(result)
        # Assert
        assert result.success is True

    @_REQUIRES_LATEXMK
    def test_compile_dark_mode_reports_dark_color_mode(self):
        # Arrange
        from scitex_writer import compile

        content = (
            r"\documentclass{article}"
            "\n"
            r"\usepackage{xcolor}"
            "\n"
            r"\usepackage{pagecolor}"
            "\n"
            r"\begin{document}"
            "\nDark mode test.\n"
            r"\end{document}"
            "\n"
        )
        # Act
        result = compile.content(content, color_mode="dark", name="test_dark")
        _cleanup_temp_dir(result)
        # Assert
        assert result.color_mode == "dark"

    @_REQUIRES_LATEXMK
    def test_compile_invalid_latex_reports_failure(self):
        # Arrange
        from scitex_writer import compile

        content = (
            r"\documentclass{article}"
            "\n"
            r"\begin{document}"
            "\n"
            r"\invalid_command_that_does_not_exist"
            "\n"
            r"\end{document}"
            "\n"
        )
        # Act
        result = compile.content(content, name="test_invalid")
        _cleanup_temp_dir(result)
        # Assert
        assert result.success is False

    @_REQUIRES_LATEXMK
    def test_compile_returns_success_key_regardless_of_timeout(self):
        # Arrange
        from scitex_writer import compile

        content = (
            r"\documentclass{article}"
            "\n"
            r"\begin{document}"
            "\nTest\n"
            r"\end{document}"
            "\n"
        )
        # Act
        # timeout=1 may or may not trip depending on machine speed; the
        # contract under test is only that the result carries a `success`
        # attribute and an `exit_code` attribute regardless of which
        # branch (success / latexmk-fail / TimeoutExpired) it hit.
        result = compile.content(content, timeout=1, name="test_timeout")
        _cleanup_temp_dir(result)
        # Assert
        assert hasattr(result, "success") and hasattr(result, "exit_code")


class TestMcpToolRegistration:
    """Test MCP tool registration for content."""

    def test_compile_content_tool_registered(self):
        """Test that compile_content tool is registered with MCP."""
        # Arrange
        import asyncio

        from scitex_writer._mcp import mcp

        # Act
        try:
            tools = asyncio.run(mcp.get_tools())
            tool_names = list(tools.keys())
        except AttributeError:
            tool_names = [t.name for t in asyncio.run(mcp._list_tools())]
        # Assert
        assert "writer_compile_content" in tool_names


# EOF

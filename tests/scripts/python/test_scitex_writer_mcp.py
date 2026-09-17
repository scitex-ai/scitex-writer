#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-01-27
# File: tests/python/test_scitex_writer_mcp.py

"""Tests for scitex_writer MCP module.

The MCP server exposes comprehensive tools for manuscript operations.
"""

import asyncio
from pathlib import Path


def _get_tool_names(mcp) -> list:
    """Get registered tool names across FastMCP versions."""
    try:
        tools = asyncio.run(mcp.get_tools())  # FastMCP >= 2.3
        return list(tools.keys())
    except AttributeError:
        tools = asyncio.run(mcp._list_tools())  # FastMCP 2.0–2.2
        return [t.name for t in tools]


class TestMcpModule:
    """Test MCP module functionality."""

    def test_mcp_import_mcp_is_not_none(self):
        # Arrange
        # Act
        from scitex_writer._mcp import mcp

        # Act
        # Assert
        assert mcp is not None

    def test_mcp_import_mcp_name_equals_get_mcp_server_name(self):
        # Arrange
        # Server name uses branding
        # Act
        from scitex_writer._core._branding import get_mcp_server_name
        from scitex_writer._mcp import mcp

        # Act
        # Assert
        assert mcp.name == get_mcp_server_name()

    def test_instructions_via_branding(self):
        """Test that instructions are available via branding module."""
        # Arrange
        from scitex_writer._core._branding import get_mcp_instructions

        # Act
        instructions = get_mcp_instructions()
        # Assert
        assert (
            (instructions is not None)
            and (isinstance(instructions, str))
            and ("manuscript" in instructions)
        )

    def test_run_server_function_exists(self):
        """Test that run_server function exists."""
        # Arrange
        # Act
        from scitex_writer._mcp import run_server

        # Assert
        assert callable(run_server)


class TestToolRegistration:
    """Test that the usage tool is registered."""

    def test_usage_tool_registered(self):
        """Test that usage tool is registered with MCP."""
        # Arrange
        # Act
        from scitex_writer._mcp import mcp

        # Assert
        assert "get_usage" in _get_tool_names(mcp)

    def test_tool_count_len_get_tool_names_mcp_28(self):
        """Test that expected number of tools are registered."""
        # Arrange
        # Act
        from scitex_writer._mcp import mcp

        # 30+ tools: usage(1), project(4), compile(4), tables(5), figures(5),
        # bib(6), guidelines(3), prompts(1), export(1), claim(6), update(1)
        # Assert
        assert len(_get_tool_names(mcp)) >= 28


class TestUsageTool:
    """Test usage tool functionality."""

    def test_usage_returns_instructions(self):
        """Test usage tool returns instructions."""
        # Arrange
        # Act
        from scitex_writer._mcp import mcp

        # Assert
        assert "get_usage" in _get_tool_names(mcp)


class TestInstructionsContent:
    """Test instructions content."""

    def test_instructions_has_setup(self):
        """Test that instructions contain setup instructions for a first-time user.

        They used to hand the reader `git clone <personal repo>`; the verb exists
        now, and a hand clone is how the missing-create-verb gap stayed invisible
        for weeks (blocker #1 of the standalone-readiness card).
        """
        # Arrange
        from scitex_writer._core._branding import get_mcp_instructions

        # Act
        instructions = get_mcp_instructions()
        # Assert
        assert ("create-project" in instructions) and ("scitex-writer" in instructions)

    def test_instructions_has_structure(self):
        """Test that instructions contains project structure info."""
        # Arrange
        from scitex_writer._core._branding import get_mcp_instructions

        # Act
        instructions = get_mcp_instructions()
        # Assert
        assert (
            ("00_shared/" in instructions)
            and ("01_manuscript/" in instructions)
            and ("02_supplementary/" in instructions)
            and ("03_revision/" in instructions)
        )

    def test_instructions_has_editable_files(self):
        """Test that instructions lists editable files."""
        # Arrange
        from scitex_writer._core._branding import get_mcp_instructions

        # Act
        instructions = get_mcp_instructions()
        # Assert
        assert (
            ("abstract.tex" in instructions)
            and ("introduction.tex" in instructions)
            and ("methods.tex" in instructions)
            and ("results.tex" in instructions)
            and ("discussion.tex" in instructions)
        )

    def test_instructions_has_compile_options(self):
        """Test that instructions lists compile options."""
        # Arrange
        from scitex_writer._core._branding import get_mcp_instructions

        # Act
        instructions = get_mcp_instructions()
        # Assert
        assert (
            ("--draft" in instructions)
            and ("--no_figs" in instructions)
            and ("--no_tables" in instructions)
            and ("--no_diff" in instructions)
        )

    def test_instructions_has_output_info(self):
        """Test that instructions lists output files."""
        # Arrange
        from scitex_writer._core._branding import get_mcp_instructions

        # Act
        instructions = get_mcp_instructions()
        # Assert
        assert "manuscript.pdf" in instructions

    def test_instructions_has_scitex_writer_root(self):
        """Test that instructions explains SCITEX_WRITER_ROOT."""
        # Arrange
        from scitex_writer._core._branding import get_mcp_instructions

        # Act
        instructions = get_mcp_instructions()
        # Assert
        assert ("SCITEX_WRITER_ROOT" in instructions) and ("compile.sh" in instructions)

    def test_instructions_has_revision_info(self):
        """Test that instructions mentions revision directory."""
        # Arrange
        from scitex_writer._core._branding import get_mcp_instructions

        # Act
        instructions = get_mcp_instructions()
        # Assert
        assert "03_revision" in instructions

    def test_instructions_has_bib_merge(self):
        """Test that instructions explains bib auto-merge."""
        # Arrange
        from scitex_writer._core._branding import get_mcp_instructions

        # Act
        instructions = get_mcp_instructions()
        # Assert
        assert ("bib_files/" in instructions) and (
            "auto-merge" in instructions.lower() or "merge" in instructions.lower()
        )


class TestHandlersModule:
    """Test handlers module can be imported."""

    def test_handlers_import_handlers_is_not_none(self):
        """Test that handlers module can be imported."""
        # Arrange
        # Act
        from scitex_writer._mcp import handlers

        # Assert
        assert handlers is not None

    def test_handlers_functions_exist(self):
        """Test that all handler functions exist (not registered, but available)."""
        # Arrange
        # Act
        from scitex_writer._mcp import handlers

        # Assert
        assert (
            (callable(handlers.clone_project))
            and (callable(handlers.compile_manuscript))
            and (callable(handlers.compile_supplementary))
            and (callable(handlers.compile_revision))
            and (callable(handlers.get_project_info))
            and (callable(handlers.get_pdf))
            and (callable(handlers.list_document_types))
            and (callable(handlers.csv_to_latex))
            and (callable(handlers.latex_to_csv))
            and (callable(handlers.pdf_to_images))
            and (callable(handlers.list_figures))
            and (callable(handlers.convert_figure))
        )


class TestUtilsModule:
    """Test utils module."""

    def test_utils_import_callable_resolve_project_path_and_callable_run_com(self):
        """Test that utils module can be imported."""
        # Arrange
        # Act
        from scitex_writer._mcp.utils import resolve_project_path, run_compile_script

        # Assert
        assert (callable(resolve_project_path)) and (callable(run_compile_script))

    def test_resolve_project_path_relative(self):
        """Test resolve_project_path with relative path."""
        # Arrange
        from scitex_writer._mcp.utils import resolve_project_path

        # Act
        result = resolve_project_path(".")
        # Assert
        assert result.is_absolute()

    def test_resolve_project_path_absolute(self):
        """Test resolve_project_path with absolute path."""
        # Arrange
        from scitex_writer._mcp.utils import resolve_project_path

        # Act
        result = resolve_project_path("/tmp")
        # Assert
        assert result == Path("/tmp")


class TestBranding:
    """Test branding module functionality."""

    def test_default_brand_values(self):
        """Test default branding values."""
        # Arrange
        # Act
        from scitex_writer._core._branding import BRAND_ALIAS, BRAND_NAME

        # Default values when env vars not set
        # Assert
        assert (BRAND_NAME == "scitex-writer") and (BRAND_ALIAS == "sw")

    def test_get_mcp_server_name(self):
        """Test MCP server name generation."""
        # Arrange
        from scitex_writer._core._branding import get_mcp_server_name

        # Should replace dots with hyphens
        # Act
        name = get_mcp_server_name()
        # Assert
        assert "." not in name

    def test_rebrand_text_noop(self):
        """Test rebrand_text returns original when no branding change."""
        # Arrange
        from scitex_writer._core._branding import rebrand_text

        text = "import scitex_writer as sw"
        # Act
        result = rebrand_text(text)
        # Assert
        assert result == text

    def test_rebrand_text_none(self):
        """Test rebrand_text handles None."""
        # Arrange
        from scitex_writer._core._branding import rebrand_text

        # Act
        result = rebrand_text(None)
        # Assert
        assert result is None


# EOF

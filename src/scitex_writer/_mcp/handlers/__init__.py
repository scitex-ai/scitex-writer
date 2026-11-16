#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/__init__.py

"""MCP Handler implementations for SciTeX Writer."""

from ._archive_pipeline import process as process_archive
from ._checks import (
    check_caption_footnote,
    check_citation_trust,
    check_float_order,
    check_limits,
    check_media_provenance,
    check_overflow,
    check_paper_symlink,
    check_ref_integrity,
    check_references,
    check_table_decimals,
)
from ._claim import (
    add_claim,
    check_claim_values,
    format_claim,
    get_claim,
    list_claims,
    remove_claim,
    render_claims,
)
from ._compile import compile_manuscript, compile_revision, compile_supplementary
from ._diff_pipeline import process as process_diff
from ._export import export_manuscript
from ._figures import convert_figure, list_figures, pdf_to_images
from ._project import clone_project, get_pdf, get_project_info, list_document_types
from ._tables import csv_to_latex, latex_to_csv
from ._tables_pipeline import process as process_tables
from ._update import update_project  # noqa: F401 -- now a package

__all__ = [
    "add_claim",
    "check_claim_values",
    "check_caption_footnote",
    "check_citation_trust",
    "check_float_order",
    "check_limits",
    "check_media_provenance",
    "check_overflow",
    "check_paper_symlink",
    "check_ref_integrity",
    "check_references",
    "check_table_decimals",
    "clone_project",
    "compile_manuscript",
    "compile_supplementary",
    "compile_revision",
    "csv_to_latex",
    "convert_figure",
    "export_manuscript",
    "format_claim",
    "get_claim",
    "get_pdf",
    "get_project_info",
    "latex_to_csv",
    "list_claims",
    "list_document_types",
    "list_figures",
    "pdf_to_images",
    "process_archive",
    "process_diff",
    "process_tables",
    "remove_claim",
    "render_claims",
    "update_project",
]

# EOF

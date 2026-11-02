#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Handler package — thin Django wrappers around scitex-writer internals."""

from .annotation import handle_add_annotation, handle_list_annotations
from .bib import handle_bib_entries, handle_bib_files
from .claim import (
    handle_add_claim,
    handle_claim_chain,
    handle_get_claim,
    handle_list_claims,
    handle_remove_claim,
    handle_render_claims,
)
from .compile import handle_compile, handle_compile_status, handle_pdf
from .core import handle_ping, handle_project_info
from .preview import handle_section_pdf, handle_section_preview
from .files import handle_file, handle_list_files, handle_sections
from .hints import handle_hints
from .media import handle_figures, handle_tables, handle_thumbnail
from .scholar import (
    handle_scholar_add_to_manuscript,
    handle_scholar_enrich,
    handle_scholar_library,
    handle_scholar_status,
)
from .viewer import handle_citation, handle_claims_metadata, handle_dag

# Endpoints where method on the same path selects a different handler are
# handled by the dispatcher itself; the map below resolves exact endpoint
# strings (after the leading slash) to (handler, allowed_methods) tuples.

# fmt: off
HANDLERS = {
    # Core
    "ping":                   (handle_ping,           ("GET",)),
    "api/project-info":       (handle_project_info,   ("GET",)),

    # Files
    "api/files":              (handle_list_files,     ("GET",)),
    "api/file":               (handle_file,           ("GET", "POST")),
    "api/sections":           (handle_sections,       ("GET",)),

    # Compile
    "api/compile":            (handle_compile,        ("POST",)),
    "api/compile/status":     (handle_compile_status, ("GET",)),
    "api/pdf":                (handle_pdf,            ("GET",)),

    "api/preview":            (handle_section_preview, ("POST",)),
    "api/preview/pdf":        (handle_section_pdf,     ("GET",)),

    # Bibliography
    "api/bib/files":          (handle_bib_files,      ("GET",)),
    "api/bib/entries":        (handle_bib_entries,    ("GET",)),

    # Media
    "api/figures":            (handle_figures,        ("GET",)),
    "api/tables":             (handle_tables,         ("GET",)),
    "api/thumbnail":          (handle_thumbnail,      ("GET",)),

    # Viewer (claims overlay + DAG + citation verification)
    "api/claims-metadata":    (handle_claims_metadata, ("GET",)),
    "api/dag":                (handle_dag,            ("GET",)),

    # Manuscript hints feed (dynamic-paper inline hints)
    "api/hints":              (handle_hints,          ("GET",)),

    # Scholar bridge (optional; degrades when scitex-scholar absent)
    "api/scholar/status":            (handle_scholar_status,            ("GET",)),
    "api/scholar/library":           (handle_scholar_library,           ("GET",)),
    "api/scholar/enrich":            (handle_scholar_enrich,            ("POST",)),
    "api/scholar/add-to-manuscript": (handle_scholar_add_to_manuscript, ("POST",)),

    # Annotations (spike 0: persist + emit one text-comment; POST/GET)
    "api/annotations":        (None,                  ("GET", "POST")),  # dispatched by method

    # Claims (non-parameterized)
    "api/claims":             (None,                  ("GET", "POST")),  # dispatched by method
    "api/claims/render":      (handle_render_claims,  ("POST",)),
}
# fmt: on

__all__ = [
    "HANDLERS",
    "handle_add_annotation",
    "handle_add_claim",
    "handle_list_annotations",
    "handle_citation",  # dispatched parametrically by views.api_dispatch
    "handle_claim_chain",
    "handle_get_claim",
    "handle_hints",
    "handle_list_claims",
    "handle_remove_claim",
]

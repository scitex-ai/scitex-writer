#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_compile.py

"""Compilation handlers: manuscript, supplementary, revision."""

from ...workspace_layout import resolve_workspace
from ..utils import resolve_project_path, run_compile_script


def _prepare(project_path, doc_type: str) -> None:
    """Run the two fail-loud pre-compile steps, recording a REFUSAL if one raises.

    Both steps raise before the engine starts, so a raise here is a refusal
    (the manuscript was never judged), not a compile failure. The exception
    is re-raised unchanged -- the record is added, the behaviour is not.
    """
    from ..._compile._event_log import EVENT_REFUSAL, record_event

    try:
        _auto_render_claims(project_path)
    except Exception as exc:
        record_event(
            project_path,
            EVENT_REFUSAL,
            reason="claims-render-failed",
            doc_type=doc_type,
            entry_point="mcp",
            detail=f"{type(exc).__name__}: {exc}",
        )
        raise
    try:
        _inject_version_stamp(project_path)
    except Exception as exc:
        record_event(
            project_path,
            EVENT_REFUSAL,
            reason="version-stamp-failed",
            doc_type=doc_type,
            entry_point="mcp",
            detail=f"{type(exc).__name__}: {exc}",
        )
        raise


def _auto_render_claims(project_path) -> None:
    """Regenerate claims_rendered.tex from claims.json (\\vclaim SSoT), fail loud.

    claims.json is the source of truth for \\vclaim values; a stale
    claims_rendered.tex would ship outdated values into the PDF. If claims.json
    is absent there is nothing to render. If rendering fails, raise rather than
    compile with a stale file — a render failure when claims.json is present is
    always a defect (malformed JSON / broken claim definition).
    """
    claims_json = project_path / "00_shared" / "claims.json"
    if not claims_json.exists():
        return
    from ._claim import render_claims

    result = render_claims(str(project_path))
    if not result.get("success"):
        raise RuntimeError(
            f"Failed to render claims_rendered.tex from {claims_json}: "
            f"{result.get('error', 'unknown error')}. Fix claims.json or the "
            f"claim definitions; compiling now would ship a stale "
            f"claims_rendered.tex."
        )


def _inject_version_stamp(project_path) -> None:
    """Write 00_shared/scitex_writer_version.tex for PDF metadata.

    Fails loud, like _render_claims above: this stamp is the manuscript's
    provenance claim about the engine that built it. Stamping a version we
    cannot establish would ship a paper asserting it was built by something
    that did not build it, and swallowing a write failure would make a stamp
    that never happened indistinguishable from a clean compile.
    """
    from ._version_truth import stamp_version, version_stamp_tex

    version = stamp_version()
    version_tex = project_path / "00_shared" / "scitex_writer_version.tex"
    version_tex.write_text(version_stamp_tex(version))


def compile_manuscript(
    project_dir: str,
    timeout: int = 300,
    no_figs: bool = False,
    no_tables: bool = False,
    no_diff: bool = False,
    draft: bool = False,
    dark_mode: bool = False,
    quiet: bool = False,
    verbose: bool = False,
    engine: str | None = None,
) -> dict:
    """Compile manuscript to PDF.

    ``project_dir`` may be the project ROOT or the writer WORKSPACE; the leaf
    owns root→workspace (scitex-hub leaf-v2 contract) and composes every
    workspace-relative path (00_shared/, compile.sh, logs/) through
    :func:`resolve_workspace` so a ROOT passed by the hub no longer fails with
    a bare FileNotFoundError on ``root/00_shared/...``.
    """
    project_path = resolve_workspace(resolve_project_path(project_dir))
    _prepare(project_path, "manuscript")
    return run_compile_script(
        project_path,
        "manuscript",
        timeout=timeout,
        no_figs=no_figs,
        no_tables=no_tables,
        no_diff=no_diff,
        draft=draft,
        dark_mode=dark_mode,
        quiet=quiet,
        verbose=verbose,
        engine=engine,
    )


def compile_supplementary(
    project_dir: str,
    timeout: int = 300,
    no_figs: bool = False,
    no_tables: bool = False,
    no_diff: bool = False,
    draft: bool = False,
    dark_mode: bool = False,
    quiet: bool = False,
    engine: str | None = None,
) -> dict:
    """Compile supplementary materials to PDF."""
    project_path = resolve_workspace(resolve_project_path(project_dir))
    _prepare(project_path, "supplementary")
    return run_compile_script(
        project_path,
        "supplementary",
        timeout=timeout,
        no_figs=no_figs,
        no_tables=no_tables,
        no_diff=no_diff,
        draft=draft,
        dark_mode=dark_mode,
        quiet=quiet,
        engine=engine,
    )


def compile_revision(
    project_dir: str,
    track_changes: bool = False,
    timeout: int = 300,
    no_diff: bool = True,
    draft: bool = False,
    dark_mode: bool = False,
    quiet: bool = False,
    engine: str | None = None,
) -> dict:
    """Compile revision document to PDF."""
    project_path = resolve_workspace(resolve_project_path(project_dir))
    _prepare(project_path, "revision")
    return run_compile_script(
        project_path,
        "revision",
        timeout=timeout,
        no_diff=no_diff,
        draft=draft,
        dark_mode=dark_mode,
        quiet=quiet,
        track_changes=track_changes,
        engine=engine,
    )


# EOF

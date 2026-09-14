#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-01-20
# File: src/scitex_writer/_mcp/utils.py

"""Utility functions for SciTeX Writer MCP handlers."""

import subprocess
import time
from pathlib import Path


def resolve_project_path(project_dir: str) -> Path:
    """Resolve project directory to absolute path."""
    project_path = Path(project_dir)
    if not project_path.is_absolute():
        project_path = Path.cwd() / project_path
    return project_path.resolve()


def run_compile_script(
    project_dir: Path,
    doc_type: str,
    timeout: int = 300,
    no_figs: bool = False,
    no_tables: bool = False,
    no_diff: bool = False,
    draft: bool = False,
    dark_mode: bool = False,
    quiet: bool = False,
    verbose: bool = False,
    track_changes: bool = False,
    engine: str | None = None,
) -> dict:
    """Run compile.sh script with specified options.

    Every call leaves records in the workspace event log
    (:mod:`scitex_writer._compile._event_log`): an ``attempt`` first, then
    exactly one of ``success`` / ``failure`` / ``refusal``. A missing
    compile.sh is a REFUSAL (the engine was never started); everything after
    the subprocess launches is a failure or a success.
    """
    from .._compile._artifacts import (
        _PROMOTED_WARNING,
        EXIT_PROMOTED_WITH_WARNINGS,
        _doc_latex_log,
    )
    from .._compile._diagnostics import diagnose_compile, diagnose_exception
    from .._compile._diagnostics._rules import MISSING_COMPILE_SCRIPT_HINT
    from .._compile._event_log import (
        EVENT_ATTEMPT,
        EVENT_FAILURE,
        EVENT_REFUSAL,
        EVENT_SUCCESS,
        new_attempt_id,
        record_event,
    )
    from .._utils._pdf_pages import produced_page_count
    from ..workspace_layout import refresh_vendored_scripts

    # Self-heal the workspace's vendored scripts from the INSTALLED package
    # before the engine runs. A workspace is a full template clone that would
    # otherwise keep stale scripts forever (2026-09-14 hub repro: an EXISTING
    # workspace — created before the fix — carried the OLD
    # check_dependancy_commands.sh, so the conditional dep-check never reached
    # the compile and it refused on xlsx2csv/csv2latex). run_compile_script is
    # the single choke point every compile (MCP handler AND the _django editor
    # path) flows through, so healing here covers fresh and existing workspaces
    # alike. Idempotent + version-gated: a no-op when already in step; touches
    # only <workspace>/scripts/..., never user content.
    try:
        refresh_vendored_scripts(project_dir)
    except Exception:  # pragma: no cover - defensive: never block a compile
        pass

    compile_script = project_dir / "compile.sh"
    attempt_id = new_attempt_id()
    record_event(
        project_dir,
        EVENT_ATTEMPT,
        doc_type=doc_type,
        entry_point="mcp",
        attempt_id=attempt_id,
        detail=f"compile.sh {doc_type}",
        extra={"engine": engine, "draft": draft, "timeout_s": timeout},
    )

    if not compile_script.exists():
        error = f"compile.sh not found at {compile_script}"
        record_event(
            project_dir,
            EVENT_REFUSAL,
            reason="workspace-missing",
            doc_type=doc_type,
            entry_point="mcp",
            attempt_id=attempt_id,
            detail=error,
        )
        return {
            "success": False,
            "error": error,
            "diagnostics": diagnose_exception(
                error, cause="missing-file", hint=MISSING_COMPILE_SCRIPT_HINT
            ),
        }

    # Build command
    cmd = ["env", "-u", "BASH_ENV", "/bin/bash", str(compile_script), doc_type]

    if no_figs:
        cmd.append("--no_figs")
    if no_tables:
        cmd.append("--no_tables")
    if no_diff:
        cmd.append("--no_diff")
    if draft:
        cmd.append("--draft")
    if dark_mode:
        cmd.append("--dark_mode")
    if quiet:
        cmd.append("--quiet")
    if verbose:
        cmd.append("--verbose")
    if track_changes and doc_type == "revision":
        cmd.append("--track_changes")

    # Set engine via environment variable (compile.sh reads SCITEX_WRITER_ENGINE)
    import os

    env = os.environ.copy()
    if engine:
        env["SCITEX_WRITER_ENGINE"] = engine

    # One second of slack: some filesystems store mtimes at 1 s resolution.
    started_at = time.time() - 1.0
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        # Determine output PDF path
        pdf_paths = {
            "manuscript": project_dir / "01_manuscript" / "manuscript.pdf",
            "supplementary": project_dir / "02_supplementary" / "supplementary.pdf",
            "revision": project_dir / "03_revision" / "revision.pdf",
        }
        output_pdf = pdf_paths.get(doc_type)
        pdf_present = bool(output_pdf and output_pdf.exists())
        stdout_tail = (
            result.stdout[-2_000:] if len(result.stdout) > 2_000 else result.stdout
        )
        stderr_tail = (
            result.stderr[-2_000:] if len(result.stderr) > 2_000 else result.stderr
        )

        diagnostics = diagnose_compile(
            project_dir,
            doc_type,
            exit_code=result.returncode,
            compile_failed=result.returncode != 0,
            stdout=result.stdout,
            stderr=result.stderr,
            started_at=started_at,
        )

        promoted_pdf_pages = (
            produced_page_count(output_pdf, _doc_latex_log(project_dir, doc_type))
            if result.returncode == EXIT_PROMOTED_WITH_WARNINGS and pdf_present
            else 0
        )
        if promoted_pdf_pages > 0:
            warning = _PROMOTED_WARNING.format(pages=promoted_pdf_pages)
            record_event(
                project_dir,
                EVENT_SUCCESS,
                doc_type=doc_type,
                entry_point="mcp",
                attempt_id=attempt_id,
                exit_code=result.returncode,
                output_pdf=output_pdf,
                pages=promoted_pdf_pages,
                detail=warning,
            )
            return {
                "success": True,
                "output_pdf": str(output_pdf),
                "exit_code": result.returncode,
                "stdout": stdout_tail,
                "stderr": stderr_tail,
                "warnings": [warning],
                "message": f"{doc_type.title()} compiled WITH WARNINGS",
                "diagnostics": diagnostics,
            }
        if result.returncode == 0:
            record_event(
                project_dir,
                EVENT_SUCCESS,
                doc_type=doc_type,
                entry_point="mcp",
                attempt_id=attempt_id,
                exit_code=result.returncode,
                output_pdf=output_pdf if pdf_present else None,
                detail=None
                if pdf_present
                else "exit 0 but no PDF at the expected path",
            )
            return {
                "success": True,
                "output_pdf": str(output_pdf) if pdf_present else None,
                "exit_code": result.returncode,
                "stdout": stdout_tail,
                "message": f"{doc_type.title()} compiled successfully",
                "diagnostics": diagnostics,
            }
        else:
            error = f"Compilation failed with exit code {result.returncode}"
            record_event(
                project_dir,
                EVENT_FAILURE,
                reason="engine-nonzero",
                doc_type=doc_type,
                entry_point="mcp",
                attempt_id=attempt_id,
                exit_code=result.returncode,
                output_pdf=output_pdf if pdf_present else None,
                stderr=result.stderr,
                detail=error,
            )
            return {
                "success": False,
                "exit_code": result.returncode,
                "stdout": stdout_tail,
                "stderr": stderr_tail,
                "error": error,
                "diagnostics": diagnostics,
            }

    except subprocess.TimeoutExpired as expired:
        error = f"Compilation timed out after {timeout} seconds"
        record_event(
            project_dir,
            EVENT_FAILURE,
            reason="timeout",
            doc_type=doc_type,
            entry_point="mcp",
            attempt_id=attempt_id,
            detail=error,
            duration=float(timeout),
        )
        return {
            "success": False,
            "error": error,
            "diagnostics": diagnose_compile(
                project_dir,
                doc_type,
                exit_code=None,
                compile_failed=True,
                stdout=_as_text(expired.stdout),
                stderr=_as_text(expired.stderr),
                started_at=started_at,
                timed_out_after_seconds=timeout,
            ),
        }
    except Exception as e:
        record_event(
            project_dir,
            EVENT_FAILURE,
            reason="exception",
            doc_type=doc_type,
            entry_point="mcp",
            attempt_id=attempt_id,
            detail=f"{type(e).__name__}: {e}",
        )
        return {
            "success": False,
            "error": str(e),
            "diagnostics": diagnose_exception(e),
        }


def _as_text(output: bytes | str | None) -> str:
    if isinstance(output, bytes):
        return output.decode("utf-8", "replace")
    return output or ""


__all__ = ["resolve_project_path", "run_compile_script"]

# EOF

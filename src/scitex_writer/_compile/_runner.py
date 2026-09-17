#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_runner.py

"""
Compilation script execution.

Executes LaTeX compilation scripts and captures results.
"""

from __future__ import annotations

import os
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import Callable, Optional

from .._dataclasses import CompilationResult
from ..workspace_layout import (
    COMPILE_SCRIPT_RELPATHS,
    WORKSPACE_RELPATH,
    compile_script_relpath,
)

# The WHERE questions (script, log, PDF) live in _artifacts; re-exported so
# existing imports of these private names from _runner keep resolving. The
# decision about what a run AMOUNTED to is not here — it is `._verdict`, which
# both compile paths call.
from ._artifacts import (
    _doc_latex_log,
    _find_output_files,
    _get_compile_script,
)
from ._event_log import (
    EVENT_ATTEMPT,
    EVENT_FAILURE,
    EVENT_REFUSAL,
    EVENT_SUCCESS,
    new_attempt_id,
    record_event,
)
from ._execute import _execute_with_callbacks, _run_sh_command
from ._parser import parse_output
from ._validator import validate_before_compile
from ._verdict import compile_verdict, engine_finished

logger = getLogger(__name__)


def run_compile(
    doc_type: str,
    project_dir: Path,
    timeout: int = 300,
    track_changes: bool = False,
    no_figs: bool = False,
    ppt2tif: bool = False,
    crop_tif: bool = False,
    quiet: bool = False,
    verbose: bool = False,
    force: bool = False,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    command_runner: Optional[Callable[..., dict]] = None,
) -> CompilationResult:
    """
    Run compilation script and parse results with optional callbacks.

    Parameters
    ----------
    doc_type : str
        Document type ('manuscript', 'supplementary', 'revision')
    project_dir : Path
        Path to project directory (containing 01_manuscript/, etc.)
    timeout : int
        Timeout in seconds
    track_changes : bool
        Enable change tracking (revision only)
    no_figs : bool
        Exclude figures for quick compilation (manuscript only)
    ppt2tif : bool
        Convert PowerPoint to TIF on WSL
    crop_tif : bool
        Crop TIF images to remove excess whitespace
    quiet : bool
        Suppress detailed logs for LaTeX compilation
    verbose : bool
        Show detailed logs for LaTeX compilation
    force : bool
        Force full recompilation, ignore cache (manuscript only)
    log_callback : Optional[Callable[[str], None]]
        Called with each log line
    progress_callback : Optional[Callable[[int, str], None]]
        Called with progress updates (percent, step)

    command_runner : Optional[Callable[..., dict]]
        Executor for the non-callback path, same shape as
        :func:`_run_sh_command` (cmd, verbose, timeout, stream_output) ->
        dict. Defaults to :func:`_run_sh_command`. Exposed so callers and
        tests can supply an alternate executor without patching internals.

    Returns
    -------
    CompilationResult
        Compilation status and outputs
    """
    if command_runner is None:
        command_runner = _run_sh_command

    start_time = datetime.now()
    project_dir = Path(project_dir).absolute()

    # Helper for progress tracking
    def progress(percent: int, step: str):
        if progress_callback:
            progress_callback(percent, step)
        logger.info(f"Progress: {percent}% - {step}")

    # Helper for logging
    def log(message: str):
        if log_callback:
            log_callback(message)
        logger.info(message)

    # Progress: Starting
    progress(0, "Starting compilation...")
    log("[INFO] Starting LaTeX compilation...")

    # Every attempt leaves a durable record (see _event_log): an `attempt`
    # now, then exactly one `refusal` / `failure` / `success` below. The
    # attempt_id ties the two lines together in the log.
    attempt_id = new_attempt_id()
    record_event(
        project_dir,
        EVENT_ATTEMPT,
        doc_type=doc_type,
        entry_point="runner",
        attempt_id=attempt_id,
        extra={"track_changes": track_changes, "no_figs": no_figs, "force": force},
    )

    # Validate project structure before compilation
    try:
        progress(5, "Validating project structure...")
        validate_before_compile(project_dir, doc_type)
        log("[INFO] Project structure validated")
    except Exception as e:
        error_msg = f"[ERROR] Validation failed: {e}"
        log(error_msg)
        record_event(
            project_dir,
            EVENT_REFUSAL,
            reason="validation",
            doc_type=doc_type,
            entry_point="runner",
            attempt_id=attempt_id,
            detail=str(e),
        )
        return CompilationResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr=str(e),
            duration=0.0,
        )

    # Get compile script
    compile_script = _get_compile_script(project_dir, doc_type)
    if not compile_script:
        error_msg = (
            f"[ERROR] Unknown doc_type {doc_type!r}; expected one of "
            f"{sorted(COMPILE_SCRIPT_RELPATHS)}"
        )
        log(error_msg)
        record_event(
            project_dir,
            EVENT_REFUSAL,
            reason="unknown-doc-type",
            doc_type=doc_type,
            entry_point="runner",
            attempt_id=attempt_id,
            detail=error_msg,
        )
        return CompilationResult(
            success=False,
            exit_code=127,
            stdout="",
            stderr=error_msg,
            duration=0.0,
        )
    if not compile_script.exists():
        # Name the root we resolved AGAINST, not just the path we missed. The
        # commonest cause is being handed a project root where a workspace was
        # expected, and the absolute path alone cannot show that -- it looks
        # like a missing file rather than a wrong base directory.
        error_msg = (
            f"[ERROR] Compilation script not found: {compile_script}\n"
            f"        Resolved as <workspace>/{compile_script_relpath(doc_type)} "
            f"with <workspace> = {project_dir}\n"
            f"        If that is a PROJECT root, the workspace is one segment "
            f"down: {project_dir / WORKSPACE_RELPATH}\n"
            f"        If the workspace is right but empty, create it with "
            f"scitex_writer.ensure_workspace(<project root>)."
        )
        log(error_msg)
        record_event(
            project_dir,
            EVENT_REFUSAL,
            reason="workspace-missing",
            doc_type=doc_type,
            entry_point="runner",
            attempt_id=attempt_id,
            detail=error_msg,
        )
        return CompilationResult(
            success=False,
            exit_code=127,
            stdout="",
            stderr=error_msg,
            duration=0.0,
        )

    # Build command
    progress(10, "Preparing compilation command...")
    script_path = compile_script.absolute()
    cmd = [str(script_path)]

    # Add document-specific options
    if doc_type == "revision":
        if track_changes:
            cmd.append("--track-changes")

    elif doc_type == "manuscript":
        if no_figs:
            cmd.append("--no_figs")
        if ppt2tif:
            cmd.append("--ppt2tif")
        if crop_tif:
            cmd.append("--crop_tif")
        if quiet:
            cmd.append("--quiet")
        elif verbose:
            cmd.append("--verbose")
        if force:
            cmd.append("--force")

    elif doc_type == "supplementary":
        if not no_figs:  # For supplementary, --figs means include figures (default)
            cmd.append("--figs")
        if ppt2tif:
            cmd.append("--ppt2tif")
        if crop_tif:
            cmd.append("--crop_tif")
        if quiet:
            cmd.append("--quiet")

    log(f"[INFO] Running: {' '.join(cmd)}")
    log(f"[INFO] Working directory: {project_dir}")

    try:
        cwd_original = Path.cwd()
        os.chdir(project_dir)

        try:
            progress(15, "Executing LaTeX compilation...")

            # Use callbacks version if callbacks provided
            if log_callback:
                result_dict = _execute_with_callbacks(
                    command=cmd,
                    cwd=project_dir,
                    timeout=timeout,
                    log_callback=log_callback,
                )
            else:
                # Use simple subprocess execution
                result_dict = command_runner(
                    cmd,
                    verbose=True,
                    timeout=timeout,
                    stream_output=True,
                )

            result = type(
                "Result",
                (),
                {
                    "returncode": result_dict["exit_code"],
                    "stdout": result_dict["stdout"],
                    "stderr": result_dict["stderr"],
                },
            )()

            duration = (datetime.now() - start_time).total_seconds()
        finally:
            os.chdir(cwd_original)

        # Find output files. Exit 3 means the script PRODUCED and promoted a PDF
        # and told us so; its artifacts must be located exactly as on exit 0 --
        # blanking them out is what USED to throw away a perfectly good PDF.
        # (Whether that run is then a SUCCESS is `_verdict`'s call, one step
        # below: locating an artifact and accepting it are different questions,
        # and conflating them is how a zero-page husk became a success.)
        if engine_finished(result.returncode):
            progress(90, "Compilation finished, locating output files...")
            output_pdf, diff_pdf, log_file = _find_output_files(project_dir, doc_type)
            if output_pdf:
                log(f"[SUCCESS] PDF generated: {output_pdf}")
        else:
            output_pdf, diff_pdf, log_file = None, None, None
            log(f"[ERROR] Compilation failed with exit code {result.returncode}")

        # Parse errors and warnings
        progress(95, "Parsing compilation logs...")
        errors, warnings = parse_output(result.stdout, result.stderr, log_file=log_file)

        # A run is a success ONLY if a real PDF with pages > 0 exists. We
        # re-derive that here rather than trusting the exit code, so a shell
        # that claims success without an artifact can never become a silent
        # success: no PDF (or a zero-page husk) FAILS. This is the "produced a
        # PDF" vs "produced nothing" line.
        #
        # THE CHECK COVERS THE CLEAN PATH TOO, AND USED NOT TO. It ran only
        # under `if promoted`, so exit 3 was held to "prove you made a PDF"
        # while exit 0 was taken at its word -- the DEGRADED path verified more
        # strictly than the healthy one. A clean exit over a zero-page husk was
        # therefore reported as success by the one branch that never looked,
        # which is the false-success shape this guard exists to prevent
        # (nv-incident-compile-false-success-deficient-pdf-20260630, which asked
        # for a page-count check and only ever got half of one).
        # THE VERDICT IS SHARED (_compile/_verdict.py), NOT RE-DERIVED HERE. The
        # history above is WHY the artifact decides; the rule itself now lives in
        # exactly one place, because these two paths had already grown apart —
        # the MCP path answered "compiled successfully" for exit 0 with no PDF
        # while this one recorded `exit-zero-no-pdf`. Two verdicts that happen to
        # agree are one local edit away from disagreeing again, and the next
        # divergence would be just as invisible.
        verdict = compile_verdict(
            result.returncode, output_pdf, _doc_latex_log(project_dir, doc_type)
        )
        promoted, success, pages = verdict.promoted, verdict.success, verdict.pages
        if verdict.success:
            if verdict.warning:
                warnings.insert(0, verdict.warning)
                log(f"[WARNING] {verdict.warning}")
        else:
            output_pdf = None
            errors.insert(
                0,
                (
                    "Compile reported a promoted PDF (exit 3) but no PDF "
                    "with pages > 0 exists. Treating as a FAILURE."
                    if promoted
                    else "Compile exited 0 but produced no PDF with "
                    "pages > 0. Treating as a FAILURE: a clean exit code "
                    "is not evidence that an artifact exists."
                ),
            )
            log(f"[ERROR] {errors[0]}")

        compilation_result = CompilationResult(
            success=success,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            output_pdf=output_pdf,
            diff_pdf=diff_pdf,
            log_file=log_file,
            duration=duration,
            errors=errors,
            warnings=warnings,
            message=(
                f"Compiled WITH WARNINGS (exit {result.returncode}): "
                "a PDF was produced but the engine reported an error"
                if (promoted and success)
                else None
            ),
        )

        # The engine WAS started, so whatever follows is success or FAILURE --
        # never a refusal. Name the failure precisely: the three shapes need
        # three different fixes (read the engine errors / find why the script
        # claimed a PDF it did not make / find why exit 0 made nothing).
        pages_seen = pages if engine_finished(result.returncode) else None
        if compilation_result.success:
            record_event(
                project_dir,
                EVENT_SUCCESS,
                doc_type=doc_type,
                entry_point="runner",
                attempt_id=attempt_id,
                exit_code=result.returncode,
                output_pdf=output_pdf,
                pages=pages_seen,
                duration=duration,
                detail=compilation_result.message,
            )
        else:
            # The reason comes from the SAME verdict the success path used —
            # `_verdict` names it from the event log's own vocabulary, so the
            # record and the response cannot describe different runs.
            failure_reason = verdict.detail
            record_event(
                project_dir,
                EVENT_FAILURE,
                reason=failure_reason,
                doc_type=doc_type,
                entry_point="runner",
                attempt_id=attempt_id,
                exit_code=result.returncode,
                pages=pages_seen,
                errors=errors,
                stderr=result.stderr,
                duration=duration,
                detail=errors[0] if errors else None,
            )

        if compilation_result.success:
            progress(100, "Complete with warnings!" if promoted else "Complete!")
            log(f"[SUCCESS] Compilation succeeded in {duration:.2f}s")
        else:
            progress(100, "Compilation failed")
            if errors:
                log(f"[ERROR] Found {len(errors)} errors")

        return compilation_result

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        logger.error(f"Compilation error: {e}")
        record_event(
            project_dir,
            EVENT_FAILURE,
            reason="exception",
            doc_type=doc_type,
            entry_point="runner",
            attempt_id=attempt_id,
            detail=f"{type(e).__name__}: {e}",
            duration=duration,
        )
        return CompilationResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr=str(e),
            duration=duration,
        )


__all__ = ["run_compile"]

# EOF

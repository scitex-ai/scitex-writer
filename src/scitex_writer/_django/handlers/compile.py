#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compilation and PDF serving handlers."""

from __future__ import annotations

import json
import threading

from django.http import FileResponse, JsonResponse


def _refuse(project, reason: str, doc_type, detail: str) -> None:
    """Record that the HTTP layer declined to start a compile.

    These are REFUSALS, not compile failures: the engine never ran, and a
    reader of the event log must be able to see that without the browser.
    That distinction is the whole reason the log exists -- see
    :mod:`scitex_writer._compile._event_log`.
    """
    from scitex_writer._compile._event_log import EVENT_REFUSAL, record_event

    record_event(
        project.project_dir,
        EVENT_REFUSAL,
        reason=reason,
        doc_type=doc_type,
        entry_point="django",
        detail=detail,
    )


MAX_FULL_LOG_CHARS = 400_000


def _full_log_text(project, result: dict) -> str:
    """The console output plus the LaTeX log, for the editor's "Show full log"."""
    parts = [result.get("stdout") or "", result.get("stderr") or ""]
    log_path = (result.get("diagnostics") or {}).get("log_path")
    if log_path:
        try:
            parts.append((project.project_dir / log_path).read_text(errors="replace"))
        except OSError:
            pass
    if not any(parts):
        parts.append(result.get("error") or "")
    text = "\n".join(part for part in parts if part)
    return text[-MAX_FULL_LOG_CHARS:]


def _do_compile(project, doc_type: str, draft: bool, dark_mode: bool) -> None:
    from scitex_writer import compile as sw_compile
    from scitex_writer._compile._diagnostics import diagnose_exception
    from scitex_writer._compile._event_log import EVENT_FAILURE, record_event

    project_str = str(project.project_dir)
    kwargs = {"draft": draft, "dark_mode": dark_mode, "quiet": True}
    try:
        if doc_type == "manuscript":
            result = sw_compile.manuscript(project_str, **kwargs)
        elif doc_type == "supplementary":
            result = sw_compile.supplementary(project_str, **kwargs)
        elif doc_type == "revision":
            result = sw_compile.revision(project_str, **kwargs)
        else:
            error = f"Unknown doc_type: {doc_type}"
            _refuse(project, "bad-request", doc_type, error)
            result = {
                "success": False,
                "error": error,
                "diagnostics": diagnose_exception(
                    error, hint="Choose manuscript, supplementary or revision"
                ),
            }

        project._compile_result = result
        if isinstance(result, dict):
            project._compile_log = result.get("log") or _full_log_text(project, result)
        else:
            project._compile_log = str(result)
    except Exception as exc:
        # The compile layer records its own outcomes; this catches what
        # escaped it (claims render / version stamp raise BEFORE the engine,
        # and record their own refusal), so anything landing here is a
        # failure the lower layers did not already write down.
        record_event(
            project.project_dir,
            EVENT_FAILURE,
            reason="exception",
            doc_type=doc_type,
            entry_point="django",
            detail=f"{type(exc).__name__}: {exc}",
        )
        project._compile_result = {
            "success": False,
            "error": str(exc),
            "diagnostics": diagnose_exception(exc),
        }
        project._compile_log = str(exc)
    finally:
        project._compiling = False


def handle_compile(request, project):
    if request.method != "POST":
        _refuse(project, "method-not-allowed", None, f"{request.method} to compile")
        return JsonResponse({"error": "POST required"}, status=405)
    if project._compiling:
        _refuse(project, "busy", None, "Compilation already in progress")
        return JsonResponse({"error": "Compilation already in progress"}, status=409)

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = {}

    doc_type = data.get("doc_type", "manuscript")
    draft = bool(data.get("draft", False))
    # Dark mode from request body (current UI theme) falls back to
    # ProjectState.dark_mode which is persisted per-project.
    dark_mode = bool(data.get("dark_mode", project.dark_mode))
    project.dark_mode = dark_mode

    project._compiling = True
    project._compile_log = ""
    project._compile_result = None

    thread = threading.Thread(
        target=_do_compile,
        args=(project, doc_type, draft, dark_mode),
        daemon=True,
    )
    thread.start()

    return JsonResponse(
        {"status": "started", "doc_type": doc_type, "dark_mode": dark_mode}
    )


def handle_compile_status(request, project):
    return JsonResponse(
        {
            "compiling": project._compiling,
            "result": project._compile_result,
            "log": project._compile_log,
        }
    )


def handle_pdf(request, project):
    doc_type = request.GET.get("doc_type", "manuscript")
    pdf_map = {
        "manuscript": "01_manuscript/manuscript.pdf",
        "supplementary": "02_supplementary/supplementary.pdf",
        "revision": "03_revision/revision.pdf",
    }
    rel_path = pdf_map.get(doc_type)
    if not rel_path:
        return JsonResponse({"error": f"Unknown doc_type: {doc_type}"}, status=400)

    pdf_path = project.project_dir / rel_path
    if not pdf_path.exists():
        return JsonResponse({"error": "PDF not found. Compile first."}, status=404)

    as_attachment = request.GET.get("download") in ("1", "true")
    return FileResponse(
        open(pdf_path, "rb"),
        content_type="application/pdf",
        filename=f"{doc_type}.pdf",
        as_attachment=as_attachment,
    )

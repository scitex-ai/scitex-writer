#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_event_log.py

"""
Durable, greppable record of every compile attempt and its outcome.

Why this exists (operator, Telegram 4901, 2026-09-05):

    何がいけないのかというのはかならずログに落ちるようにしたいです。
    scitex-logging つかって、.scitex/writer/logs/ のしたとか、store とかに
    入れておくと良いですよね。

Before this module, the only trace of a compile that did not happen was
whatever the caller chose to show on screen. A person who saw "Compilation
Error" in a browser had nothing on disk to grep, and the agent who
investigated had to read the UI's source to learn that the "error" was an
authorization refusal, not a LaTeX failure. This module makes every attempt
leave a record that says WHAT was attempted, WHETHER the engine ran, and WHY
it did not produce a PDF -- in a place a person can open without the UI.

WHERE:  ``<workspace>/logs/compile-events.jsonl`` where ``<workspace>`` is
``<project>/.scitex/writer/`` (see :mod:`scitex_writer.workspace_layout`).
One JSON object per line, append-only, UTC timestamps. The same record is
also emitted through ``scitex_logging.getLogger("scitex_writer.compile")`` so
it joins whatever sink the host process has configured.

THE ONE DISTINCTION THIS LOG MUST NEVER FLATTEN -- refusal vs failure:

* ``refusal``  -- scitex-writer DECLINED TO START the engine. The project was
  not compiled because a precondition or an authorization check said no:
  the workspace is missing, the doc_type is unknown, a compile is already
  running, claims could not be rendered, ... The LaTeX source was never
  judged. Fixing a refusal means satisfying the precondition, not editing
  the manuscript.
* ``failure``  -- the engine WAS STARTED and no usable PDF came out: a
  non-zero exit, a timeout, an exception mid-run, or a "success" exit with
  no PDF behind it. Fixing a failure means reading the engine's errors.

A UI that renders both under one heading reproduces the defect this module
was written to expose; a log that did the same would reproduce it one layer
down. So ``kind`` is a separate field from ``reason``, and the two reason
vocabularies (:data:`REFUSAL_REASONS`, :data:`FAILURE_REASONS`) are
disjoint by construction -- :func:`record_event` rejects a reason from the
wrong vocabulary rather than writing an ambiguous record.

Failure to WRITE the log is itself reported (to stderr and the logger) and
never masks the compile outcome: a compile must not fail because its log
could not be appended, but the missing record must not be silent either.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Union

from scitex_logging import getLogger

from .._dataclasses.config import DOC_TYPE_DIRS
from ..workspace_layout import SHELL_SCRIPTS_RELPATH, WORKSPACE_RELPATH

logger = getLogger("scitex_writer.compile")

PathLike = Union[str, "os.PathLike[str]"]

LOG_RELPATH = Path("logs") / "compile-events.jsonl"
"""Where the event log lives, relative to the WORKSPACE (not the project)."""

EVENT_ATTEMPT = "attempt"
EVENT_SUCCESS = "success"
EVENT_FAILURE = "failure"
EVENT_REFUSAL = "refusal"
EVENT_KINDS = frozenset({EVENT_ATTEMPT, EVENT_SUCCESS, EVENT_FAILURE, EVENT_REFUSAL})

REFUSAL_REASONS = frozenset(
    {
        "busy",  # a compile for this project is already running
        "method-not-allowed",  # HTTP verb the compile endpoint does not take
        "bad-request",  # request named a doc_type / option that does not exist
        "unknown-doc-type",  # runner asked for a doc_type it has no script for
        "workspace-missing",  # no compile script where the workspace should be
        "validation",  # project structure failed the pre-compile validator
        "claims-render-failed",  # claims.json present but could not be rendered
        "version-stamp-failed",  # could not write the provenance stamp
    }
)
"""Reasons the engine was NOT STARTED. Disjoint from :data:`FAILURE_REASONS`."""

FAILURE_REASONS = frozenset(
    {
        "engine-nonzero",  # engine ran, exited non-zero, no promoted PDF
        "promoted-without-pdf",  # exit 3 claimed a PDF; none with pages > 0 exists
        "exit-zero-no-pdf",  # exit 0 but no PDF with pages > 0 exists
        "timeout",  # engine exceeded the caller's timeout
        "exception",  # Python raised while the engine was being run
    }
)
"""Reasons the engine WAS STARTED and yielded no usable PDF."""

assert not (REFUSAL_REASONS & FAILURE_REASONS), "reason vocabularies must be disjoint"

STDERR_TAIL_CHARS = 2_000


def workspace_for(project_or_workspace: PathLike) -> Path:
    """Resolve the WORKSPACE a caller's path refers to.

    Callers hand this module whichever directory they were handed
    themselves: the Django and MCP paths receive the workspace
    (``<project>/.scitex/writer``), the ``Writer`` class receives a project
    root. Both must land on the same log file, so:

    * if ``<path>`` itself carries a workspace marker (``compile.sh``,
      ``scripts/shell/`` or ``01_manuscript/``), it IS the workspace;
    * else if ``<path>/.scitex/writer`` exists, ``<path>`` is a project root
      and the workspace is that subdirectory;
    * otherwise ``<path>`` is taken to be the workspace itself.

    The marker check comes FIRST because the workspace template ships its
    own nested ``.scitex/writer`` directory: testing for the nested dir
    alone resolved a real workspace one level too deep and put the log
    under ``<workspace>/.scitex/writer/logs/`` (measured 2026-09-05 on a
    freshly scaffolded project).

    No filesystem is created here; that happens on the first write.
    """
    path = Path(project_or_workspace).absolute()
    if _looks_like_workspace(path):
        return path
    nested = path / WORKSPACE_RELPATH
    if nested.is_dir():
        return nested
    return path


def _looks_like_workspace(path: Path) -> bool:
    return (
        (path / "compile.sh").is_file()
        or (path / SHELL_SCRIPTS_RELPATH).is_dir()
        or (path / DOC_TYPE_DIRS["manuscript"]).is_dir()
    )


def events_log_path(project_or_workspace: PathLike) -> Path:
    """Absolute path of the event log for this project / workspace."""
    return workspace_for(project_or_workspace) / LOG_RELPATH


def new_attempt_id() -> str:
    """Correlates the ``attempt`` record with its outcome record."""
    return uuid.uuid4().hex[:12]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _tail(text: Optional[str], limit: int = STDERR_TAIL_CHARS) -> Optional[str]:
    if not text:
        return None
    return text[-limit:] if len(text) > limit else text


def record_event(
    project_or_workspace: PathLike,
    kind: str,
    *,
    doc_type: Optional[str],
    entry_point: str,
    reason: Optional[str] = None,
    attempt_id: Optional[str] = None,
    detail: Optional[str] = None,
    exit_code: Optional[int] = None,
    output_pdf: Optional[PathLike] = None,
    pages: Optional[int] = None,
    errors: Optional[Iterable[str]] = None,
    stderr: Optional[str] = None,
    duration: Optional[float] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Append one event record and return it.

    ``kind`` is one of :data:`EVENT_KINDS`. ``reason`` is REQUIRED for
    ``failure`` and ``refusal`` and must come from the matching vocabulary;
    it is rejected on ``attempt`` / ``success``. ``entry_point`` names the
    code path that produced the record (``runner``, ``mcp``, ``django``) so
    a reader can tell which of writer's two compile paths was taken.

    Raises ``ValueError`` on a malformed record -- a wrong-vocabulary reason
    is a programming error in writer and must not be written as if it were
    a fact about the compile.
    """
    if kind not in EVENT_KINDS:
        raise ValueError(
            f"unknown event kind {kind!r}; expected one of {sorted(EVENT_KINDS)}"
        )
    if kind == EVENT_REFUSAL:
        if reason not in REFUSAL_REASONS:
            raise ValueError(
                f"refusal needs a reason from {sorted(REFUSAL_REASONS)}, got {reason!r}"
            )
    elif kind == EVENT_FAILURE:
        if reason not in FAILURE_REASONS:
            raise ValueError(
                f"failure needs a reason from {sorted(FAILURE_REASONS)}, got {reason!r}"
            )
    elif reason is not None:
        raise ValueError(f"{kind!r} events carry no reason, got {reason!r}")

    workspace = workspace_for(project_or_workspace)
    record: dict[str, Any] = {
        "ts": _utc_now(),
        "kind": kind,
        "reason": reason,
        "doc_type": doc_type,
        "entry_point": entry_point,
        "attempt_id": attempt_id,
        "workspace": str(workspace),
        "detail": detail,
        "exit_code": exit_code,
        "output_pdf": str(output_pdf) if output_pdf else None,
        "pages": pages,
        "errors": list(errors) if errors else None,
        "stderr_tail": _tail(stderr),
        "duration_s": round(duration, 3) if duration is not None else None,
        "pid": os.getpid(),
    }
    if extra:
        record.update(extra)

    # JSON Lines, one record per line, APPENDED: the file is a log, not an
    # artifact, and a whole-file saver would have to rewrite it on every
    # compile. Plain json is the right tool here.
    line = json.dumps(record, ensure_ascii=False, default=str)  # stx-allow: STX-IO006

    if kind == EVENT_FAILURE:
        logger.error(line)
    elif kind == EVENT_REFUSAL:
        logger.warning(line)
    else:
        logger.info(line)

    path = workspace / LOG_RELPATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        # The compile's outcome stands; the missing record must not be silent.
        msg = f"[scitex_writer.compile] could not append event log {path}: {exc}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        record["log_write_error"] = str(exc)
    return record


def read_events(project_or_workspace: PathLike) -> list[dict[str, Any]]:
    """Return every record in the event log, oldest first ([] if none)."""
    path = events_log_path(project_or_workspace)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                out.append(json.loads(raw))  # stx-allow: STX-IO006 (JSONL line)
    return out


__all__ = [
    "EVENT_ATTEMPT",
    "EVENT_FAILURE",
    "EVENT_KINDS",
    "EVENT_REFUSAL",
    "EVENT_SUCCESS",
    "FAILURE_REASONS",
    "LOG_RELPATH",
    "REFUSAL_REASONS",
    "events_log_path",
    "new_attempt_id",
    "read_events",
    "record_event",
    "workspace_for",
]

# EOF

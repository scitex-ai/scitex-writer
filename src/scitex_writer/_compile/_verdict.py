#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE compile verdict — ONE rule, and both compile paths call it.

WHY THIS MODULE EXISTS. Writer has two compile entry points: the runner
(``_compile/_runner.py``, driven by ``compile.sh`` through the MCP handlers) and
``_mcp/utils.run_compile_script`` (the single choke point the MCP tools and the
``_django`` editor flow through). Each grew its own exit-code judgement locally,
and they disagreed: exit 3 was success-with-warnings on one path and a failure
on the other, so a compile that produced a real PDF was reported as an error to
the editor while the same run was a success to the CLI.

Teaching the second path about exit 3 would fix that instance and recreate the
cause: two verdicts that HAPPEN to agree are one local edit away from disagreeing
again, and the next divergence is just as invisible — a green suite of two
per-path tests, both passing against two implementations drifting apart
(card ``scitex-writer-standalone-readiness-measured-blockers-20260902``, the
2026-09-06 14:00Z note, which prescribed this extraction rather than the copy).

So the verdict lives here, once. A path may still describe a run its own way —
the runner keeps its progress log and warnings, the MCP path keeps its response
dict — but neither may DECIDE. The rule is:

    the artifact is the truth, and the exit code only says how loud to be.

* exit 0 or exit 3 (``EXIT_PROMOTED_WITH_WARNINGS``, "produced a PDF and said
  so") means the engine finished; any other exit is a failure and no artifact is
  looked for.
* a finished engine still has to SHOW a PDF with pages > 0. A clean exit over
  nothing — or over a zero-page husk — is the false-success shape the June 2026
  incident asked for a page-count check to catch
  (``nv-incident-compile-false-success-deficient-pdf-20260630``); taking exit 0
  at its word is exactly the hole that check was meant to close.
* exit 3 with a real PDF is a success that is NOT clean, and says so through
  ``warning``.

The failure reason is drawn from the event log's own vocabulary
(``_event_log.FAILURE_REASONS``), so the record a workspace keeps and the
verdict the caller reads are the same three words.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .._utils._pdf_pages import produced_page_count
from ._artifacts import EXIT_PROMOTED_WITH_WARNINGS, _PROMOTED_WARNING

#: Failure reasons, matching ``_event_log.FAILURE_REASONS`` one for one.
REASON_ENGINE_NONZERO = "engine-nonzero"
REASON_PROMOTED_WITHOUT_PDF = "promoted-without-pdf"
REASON_EXIT_ZERO_NO_PDF = "exit-zero-no-pdf"


@dataclass(frozen=True)
class Verdict:
    """What a finished compile attempt amounts to.

    Attributes
    ----------
    success:
        A PDF with pages > 0 exists. Nothing else in this class can make it
        true.
    promoted:
        The engine exited 3: it produced a PDF and reported warnings (bibtex
        stubs, overfull boxes) rather than failing.
    pages:
        Pages seen in the produced PDF, or 0. ``pages > 0`` is what ``success``
        means.
    warning:
        The user-facing promoted warning, present only on a PROMOTED SUCCESS —
        a promoted failure is not a success with extra words, it is a failure.
    detail:
        On failure, the reason (one of this module's REASON_* values); ``None``
        on success.
    """

    success: bool
    promoted: bool
    pages: int
    warning: Optional[str]
    detail: Optional[str]


def engine_finished(exit_code: int) -> bool:
    """True when the engine ran to completion — exit 0, or the promoted exit 3.

    Callers need this BEFORE they have an artifact: it is what decides whether a
    run's output files are worth looking for at all (the runner) and whether a
    failure is "the engine died" or "the engine finished and produced nothing"
    (the event log's ``pages`` field). Kept here, beside the verdict, so the
    definition of "promoted" exists once: two spellings of it were exactly how
    the two compile paths drifted apart.
    """
    return exit_code == 0 or exit_code == EXIT_PROMOTED_WITH_WARNINGS


def compile_verdict(
    exit_code: int,
    output_pdf: Optional[Path],
    latex_log: Optional[Path] = None,
) -> Verdict:
    """Map an engine exit code and its artifact to the ONE verdict.

    Parameters
    ----------
    exit_code:
        The compile script's return code.
    output_pdf:
        The PDF this attempt expects to have produced, or ``None`` when the
        script wrote none. A path is not evidence: the page count is.
    latex_log:
        The document log, used by :func:`produced_page_count` to read a page
        count the PDF itself does not carry.

    Returns
    -------
    Verdict
        See :class:`Verdict`.
    """
    promoted = exit_code == EXIT_PROMOTED_WITH_WARNINGS

    if exit_code != 0 and not promoted:
        return Verdict(
            success=False,
            promoted=False,
            pages=0,
            warning=None,
            detail=REASON_ENGINE_NONZERO,
        )

    pages = produced_page_count(output_pdf, latex_log) if output_pdf else 0
    if pages > 0:
        return Verdict(
            success=True,
            promoted=promoted,
            pages=pages,
            warning=_PROMOTED_WARNING.format(pages=pages) if promoted else None,
            detail=None,
        )

    return Verdict(
        success=False,
        promoted=promoted,
        pages=0,
        warning=None,
        detail=(
            REASON_PROMOTED_WITHOUT_PDF if promoted else REASON_EXIT_ZERO_NO_PDF
        ),
    )


__all__ = [
    "REASON_ENGINE_NONZERO",
    "REASON_EXIT_ZERO_NO_PDF",
    "REASON_PROMOTED_WITHOUT_PDF",
    "Verdict",
    "compile_verdict",
    "engine_finished",
]

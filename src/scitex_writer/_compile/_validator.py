#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_validator.py

"""
Pre-compile validation for writer projects.

Fast, no-heavy-work checks run at the START of compilation (fail-fast) so a
broken or over-limit manuscript is rejected before any pdflatex pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scitex_logging import getLogger

from .._utils._verify_tree_structure import verify_tree_structure

logger = getLogger(__name__)


def validate_before_compile(project_dir: Path, doc_type: str = "manuscript") -> None:
    """Validate a project before compilation (cheap pre-flight, no heavy work).

    Runs in milliseconds so problems surface immediately instead of after a
    full compile:

    1. Tree-structure verification.
    2. Section word limits + reference cap from ``config/config_<doc_type>.yaml``
       (the ``limits:`` block). Over-limit is a warning and does NOT block
       unless strict mode is on (``limits.strict: true`` /
       ``SCITEX_WRITER_LINT_STRICT=1``), in which case this raises before any
       pdflatex work.
    3. Provenance/symlink checks (paper-symlink, media-provenance) at their
       configured severity. ``off``/``warn`` never block; ``error`` raises
       before any pdflatex work. Mirrors the shell compile gate so the API and
       ``./compile.sh`` paths enforce identically.
    4. ``contents/latex_styles`` must resolve into ``00_shared/latex_styles``
       (manuscript/supplementary). A local COPY silently breaks the claims/clew
       provenance render (``\\IfFileExists`` paths go stale) — always an error.

    Parameters
    ----------
    project_dir : Path
        Path to project directory.
    doc_type : str
        ``manuscript`` (default), ``supplementary``, or ``revision``.

    Raises
    ------
    RuntimeError
        If structure verification fails, a limit is exceeded under strict, a
        provenance check is at error severity with a violation, or
        ``contents/latex_styles`` has diverged from ``00_shared``.
    """
    verify_tree_structure(project_dir)
    _validate_limits(Path(project_dir), doc_type)
    _validate_provenance(Path(project_dir))
    _validate_styles_symlink(Path(project_dir), doc_type)


def _validate_limits(project_dir: Path, doc_type: str) -> None:
    """Run the fast limit check; warn (non-strict) or raise (strict)."""
    if doc_type not in ("manuscript", "supplementary", "revision"):
        return
    try:
        from .._mcp.handlers._checks import check_limits
    except Exception as exc:  # pragma: no cover - defensive import guard
        logger.info("Limit check unavailable (%s) - skipping", exc)
        return

    result = check_limits(str(project_dir), doc_type=doc_type)

    # Projects predating check_limits.py: skip quietly, never block compile.
    if not result.get("success") and "exit_code" not in result:
        logger.info("Limit check skipped: %s", result.get("error"))
        return

    findings = (result.get("stdout") or "").strip()
    summary = result.get("summary") or {}
    if summary.get("warnings") or summary.get("errors"):
        # Surface over-limit sections (feedback A->B->A, not fire-and-forget).
        sys.stderr.write(findings + "\n")

    if result.get("exit_code", 0) != 0:
        raise RuntimeError(
            "Section/reference limits exceeded in strict mode — trim the "
            "flagged sections or set limits.strict: false.\n" + findings
        )


def _provenance_runners():
    """Return the (name, callable) provenance checks, or None if unavailable.

    Lazy import so this module stays importable where the MCP handlers (and
    their deps) are absent — the compile path simply skips the checks then.
    """
    try:
        from .._mcp.handlers._checks import (
            check_media_provenance,
            check_paper_symlink,
        )
    except Exception as exc:  # pragma: no cover - defensive import guard
        logger.info("Provenance checks unavailable (%s) - skipping", exc)
        return None
    return (
        ("paper-symlink", check_paper_symlink),
        ("media-provenance", check_media_provenance),
    )


def _validate_provenance(project_dir: Path, runners=None) -> None:
    """Run the config-driven provenance checks; raise if one is at error level
    with a violation.

    paper-symlink and media-provenance each resolve their own severity
    (off|warn|error) from CLI/env/config. ``off``/``warn`` never block; ``error``
    raises before any compile work (fail-loud). Without this, setting a check to
    ``error`` was a silent no-op on the API compile path.

    ``runners`` is an injection seam (a sequence of ``(name, callable)`` pairs):
    production passes ``None`` and the real check handlers are used; tests inject
    real callables returning canned result envelopes.
    """
    if runners is None:
        runners = _provenance_runners()
    if not runners:
        return

    for name, run in runners:
        result = run(str(project_dir))
        # Projects predating the check script: skip quietly, never block compile.
        if not result.get("success") and "exit_code" not in result:
            logger.info("%s check skipped: %s", name, result.get("error"))
            continue
        findings = (result.get("stdout") or "").strip()
        summary = result.get("summary") or {}
        if summary.get("warnings") or summary.get("errors"):
            # Surface findings (feedback A->B->A, not fire-and-forget).
            sys.stderr.write(findings + "\n")
        if result.get("exit_code", 0) != 0:
            raise RuntimeError(
                f"{name} check failed at error severity — fix the violation or "
                "lower its level (off/warn).\n" + findings
            )


# Doc types whose contents/latex_styles is canonically a SYMLINK into
# 00_shared. Revision is exempt: the template ships it a real local dir.
_STYLES_SYMLINK_DOC_DIRS = {
    "manuscript": "01_manuscript",
    "supplementary": "02_supplementary",
}


def _validate_styles_symlink(project_dir: Path, doc_type: str) -> None:
    """Fail loud when ``contents/latex_styles`` no longer resolves into
    ``00_shared/latex_styles``.

    Root cause of the neurovista provenance incident (2026-07-08): the symlink
    was replaced by a local COPY, so the style files' relative ``../../00_shared``
    paths went stale and every claims/clew ``\\IfFileExists`` include silently
    skipped — provenance rendering vanished with zero diagnostics. This guard
    turns that silent divergence into an immediate, actionable compile error.
    """
    doc_dir = _STYLES_SYMLINK_DOC_DIRS.get(doc_type)
    if doc_dir is None:
        return
    styles = project_dir / doc_dir / "contents" / "latex_styles"
    shared = project_dir / "00_shared" / "latex_styles"
    if not shared.is_dir():
        # Non-canonical layout (no 00_shared) — nothing to diverge from.
        return
    fix_hint = (
        f"Fix:\n"
        f"  rm -rf {styles}\n"
        f"  ln -s ../../00_shared/latex_styles {styles}"
    )
    if styles.is_symlink() and not styles.exists():
        raise RuntimeError(
            f"{doc_dir}/contents/latex_styles is a BROKEN symlink "
            f"(-> {styles.readlink()}). {fix_hint}"
        )
    if not styles.exists():
        # Missing entirely is the tree-structure check's concern.
        return
    if styles.resolve() != shared.resolve():
        raise RuntimeError(
            f"{doc_dir}/contents/latex_styles must resolve into "
            f"00_shared/latex_styles, but resolves to {styles.resolve()} — "
            "a local copy here silently breaks claims/clew provenance "
            f"rendering (stale ../../00_shared paths). {fix_hint}"
        )


__all__ = ["validate_before_compile"]

# EOF

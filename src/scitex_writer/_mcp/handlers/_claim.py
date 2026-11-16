#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_claim.py

"""Claim handlers: CRUD through the scitex-clew claim store + LaTeX rendering.

Claims are traceable scientific assertions — statistics, values, citations, figure
references — stored as structured objects instead of magic numbers. The store
of record is scitex-clew (see ``_claim_store``): every claim registered here is
a clew claim, so it back-traces through clew's DAG to the session/file that
produced it. ``00_shared/claims.json`` is a derived export, never a second
store.

Usage in LaTeX (after render_claims is called before compile):
    \\vclaim{group_comparison}           % nature style (default)
    \\vclaim[apa]{group_comparison}      % APA style
    \\vclaim[plain]{group_comparison}    % plain text
"""

from pathlib import Path
from typing import Any, Dict, Optional

from ..utils import resolve_project_path
from ._claim_format import (
    CLAIM_TYPES,
    FORMAT_STYLES,
    _render_claim,
    _sanitize_id,
    describe_sanitize_collisions,
    find_sanitize_collisions,
)
from ._claim_paths import (  # noqa: F401  (re-exported; tests + callers use them)
    _claim_path_roots,
    _dangling_output_error,
    _output_file_exists,
    resolve_output_file,
)
from ._claim_source import check_claim_against_source
from ._claim_store import (
    CLAIMS_FILE,
    ClewUnavailableError,
    register,
    retire,
    sync,
    write_export,
)

CLAIMS_RENDERED = "00_shared/claims_rendered.tex"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _display(entry: Dict[str, Any]) -> str:
    """The display string clew carries for a claim (LaTeX-ready, nature)."""
    return _render_claim(entry, "nature")


def _load_claims(project_path: Path) -> Dict:
    """All claims of the project, FROM THE CLEW STORE (migrating claims.json).

    Raises ClewUnavailableError when clew or its store is unavailable — there
    is deliberately no fallback to reading the JSON file directly.
    """
    claims, notices = sync(Path(project_path), _display)
    return {"claims": claims, "notices": notices}


def _failure(exc: Exception) -> Dict:
    kind = "clew_unavailable" if isinstance(exc, ClewUnavailableError) else None
    out = {"success": False, "error": str(exc)}
    if kind:
        out["error_kind"] = kind
    return out


# ---------------------------------------------------------------------------
# Public handler functions
# ---------------------------------------------------------------------------


def add_claim(
    project_dir: str,
    claim_id: str,
    claim_type: str,
    value: Dict[str, Any],
    context: Optional[str] = None,
    session_id: Optional[str] = None,
    output_file: Optional[str] = None,
    output_hash: Optional[str] = None,
    test: Optional[str] = None,
    source_keys: Optional[Dict[str, Any]] = None,
    tolerance: Optional[Dict[str, float]] = None,
    tex_file: Optional[str] = None,
    line_number: Optional[int] = None,
) -> Dict:
    """Register (or update) a claim in the scitex-clew store.

    Parameters
    ----------
    project_dir : str
        Path to the scitex-writer project directory.
    claim_id : str
        Unique identifier (e.g., "group_comparison"). Used in \\vclaim{id};
        also the clew claim_id, so clew's DAG/verify output joins on it.
    claim_type : str
        One of: statistic, value, citation, figure, table.
    value : dict
        The claim's data. For statistic: {t, df, p, d} or {F, df1, df2, p, eta2}.
        For value: {value, unit}. For citation: {text}. For figure/table: {label}.
    context : str, optional
        Human-readable description of what this claim represents.
    session_id : str, optional
        Session that produced the value (clew ``source_session``; clew
        auto-detects it from ``output_file`` when omitted).
    output_file : str, optional
        File that produced this value (clew ``source_file``; hashed by clew).
    output_hash : str, optional
        SHA-256 of output_file when the value was computed. If given and the
        file's CURRENT hash differs, registration is REFUSED.
    test : str, optional
        Statistical test name (e.g., "welch_t_test") for statistic claims.
    source_keys : dict, optional
        Where each value field lives inside ``output_file``, so the pre-compile
        check can re-read and compare it: ``{"<field>": locator}``, locator =
        ``{"pointer": "/a/0/b"}`` (json/yaml, RFC 6901) or
        ``{"row": 3 | {"col": "val"}, "column": "name" | 2}`` (csv/tsv), with
        optional per-field ``abs_tol`` / ``rel_tol``. Field ``"."`` = the
        whole (scalar) value. A claim that already disagrees with its source
        is REFUSED.
    tolerance : dict, optional
        Claim-level ``{"abs_tol": x, "rel_tol": y}``; when nothing is declared
        the tolerance is implied by the precision the value is written with.
    tex_file, line_number : optional
        Manuscript location of the claim; default = the first
        ``\\vclaim{claim_id}`` call site found in the project's contents.

    Returns
    -------
    dict
        Success status, rendered preview for each style, and clew notices.
    """
    try:
        if claim_type not in CLAIM_TYPES:
            return {
                "success": False,
                "error": f"Invalid claim_type '{claim_type}'. Must be one of: {CLAIM_TYPES}",
            }

        project_path = resolve_project_path(project_dir).resolve()
        # Migrate any legacy claims.json BEFORE writing, so a migration can
        # never overwrite the claim being added now.
        _, notices = sync(project_path, _display)

        entry: Dict[str, Any] = {
            "type": claim_type,
            "value": value,
            "context": context,
            "session_id": session_id,
            "output_file": output_file,
            "output_hash": output_hash,
            "source_keys": source_keys,
            "tolerance": tolerance,
        }
        if test:
            entry["test"] = test

        notices = notices + register(
            project_path,
            claim_id,
            entry,
            _display(entry),
            tex_file=tex_file,
            line_number=line_number,
        )
        claims, more = sync(project_path, _display)
        stored = claims.get(claim_id)
        if stored is None:
            raise ClewUnavailableError(
                f"clew accepted claim {claim_id!r} but it is not readable back "
                "from the store; refusing to report success."
            )

        previews = {style: _render_claim(stored, style) for style in FORMAT_STYLES}

        return {
            "success": True,
            "claim_id": claim_id,
            "claim_type": claim_type,
            "store": "scitex-clew",
            "location": {
                "file": stored.get("file_path"),
                "line": stored.get("line_number"),
            },
            "previews": previews,
            "latex_usage": f"\\vclaim{{{claim_id}}}",
            "notices": notices + more,
        }
    except Exception as e:  # incl. ClewUnavailableError -> success False, loud
        return _failure(e)


def list_claims(project_dir: str) -> Dict:
    """List all claims in the project (from the clew store).

    Parameters
    ----------
    project_dir : str
        Path to the scitex-writer project directory.

    Returns
    -------
    dict
        List of claims with formatted previews.
    """
    try:
        project_path = resolve_project_path(project_dir).resolve()
        data = _load_claims(project_path)
        claims = data.get("claims", {})

        result = []
        for claim_id, claim in claims.items():
            preview = _render_claim(claim, "nature")
            session_id = claim.get("session_id")
            output_file = claim.get("output_file")
            output_exists = _output_file_exists(project_path, output_file)
            result.append(
                {
                    "claim_id": claim_id,
                    "type": claim.get("type", "unknown"),
                    "context": claim.get("context", ""),
                    "preview_nature": preview,
                    # The POINTERS, not just the boolean: callers verify a claim's
                    # chain with these. Summarising them away as `has_provenance`
                    # left the viewer unable to verify anything, so every claim
                    # came back NO_PROVENANCE — including the ones that had it.
                    "session_id": session_id,
                    "output_file": output_file,
                    "output_file_exists": output_exists,
                    # A pointer to a file that IS NOT THERE is not provenance.
                    # This used to be `bool(session_id or output_file)` — true for
                    # any non-empty string — so a claim whose output was deleted,
                    # renamed, or never written still reported "this claim has
                    # provenance". paper-scitex-clew found 24 of 49 claims in a
                    # real manuscript in exactly that state, every one of them
                    # claiming provenance it did not have. That is a confident
                    # wrong answer about the science, which is worse than an
                    # admitted gap.
                    "has_provenance": bool(session_id or output_exists),
                    "provenance_error": _dangling_output_error(
                        output_file, output_exists
                    ),
                    "status": claim.get("status"),
                    "has_source_keys": bool(claim.get("source_keys")),
                }
            )

        return {
            "success": True,
            "count": len(result),
            "claims": result,
            "store": "scitex-clew",
            "notices": data["notices"],
        }
    except Exception as e:
        return _failure(e)


def get_claim(project_dir: str, claim_id: str) -> Dict:
    """Get details of a specific claim.

    Parameters
    ----------
    project_dir : str
        Path to the scitex-writer project directory.
    claim_id : str
        Claim identifier.

    Returns
    -------
    dict
        Full claim data including rendered previews for all styles.
    """
    try:
        project_path = resolve_project_path(project_dir).resolve()
        data = _load_claims(project_path)
        claim = data.get("claims", {}).get(claim_id)

        if claim is None:
            return {"success": False, "error": f"Claim not found: '{claim_id}'"}

        previews = {style: _render_claim(claim, style) for style in FORMAT_STYLES}

        return {
            "success": True,
            "claim_id": claim_id,
            "claim": claim,
            "previews": previews,
            "latex_usage": f"\\vclaim{{{claim_id}}}",
        }
    except Exception as e:
        return _failure(e)


def remove_claim(project_dir: str, claim_id: str) -> Dict:
    """Retire a claim (clew ``supersede_claim``) and refresh the export.

    Parameters
    ----------
    project_dir : str
        Path to the scitex-writer project directory.
    claim_id : str
        Claim identifier to remove.

    Returns
    -------
    dict
        Success status.
    """
    try:
        project_path = resolve_project_path(project_dir).resolve()
        data = _load_claims(project_path)

        if claim_id not in data.get("claims", {}):
            return {"success": False, "error": f"Claim not found: '{claim_id}'"}

        if not retire(project_path, claim_id):
            return {
                "success": False,
                "error": f"clew could not retire claim '{claim_id}'",
            }
        remaining = {k: v for k, v in data["claims"].items() if k != claim_id}
        write_export(project_path, remaining)

        return {"success": True, "removed": claim_id, "store": "scitex-clew"}
    except Exception as e:
        return _failure(e)


def format_claim(project_dir: str, claim_id: str, style: str = "nature") -> Dict:
    """Format a claim as a LaTeX string.

    Parameters
    ----------
    project_dir : str
        Path to the scitex-writer project directory.
    claim_id : str
        Claim identifier.
    style : str
        Format style: 'nature' (default), 'apa', or 'plain'.

    Returns
    -------
    dict
        Formatted LaTeX string for the claim.
    """
    try:
        if style not in FORMAT_STYLES:
            return {
                "success": False,
                "error": f"Invalid style '{style}'. Must be one of: {FORMAT_STYLES}",
            }

        project_path = resolve_project_path(project_dir).resolve()
        data = _load_claims(project_path)
        claim = data.get("claims", {}).get(claim_id)

        if claim is None:
            return {"success": False, "error": f"Claim not found: '{claim_id}'"}

        rendered = _render_claim(claim, style)

        return {
            "success": True,
            "claim_id": claim_id,
            "style": style,
            "rendered": rendered,
        }
    except Exception as e:
        return _failure(e)


def check_claim_values(project_dir: str) -> Dict:
    """Re-read every located claim value from its source and compare.

    For each claim registered with ``source_keys``, the value at each locator
    is read from the claim's ``output_file`` NOW and compared with the claim's
    value field within the declared (or precision-implied) tolerance. This is
    the value-level complement of clew's hash check: a hash proves the file is
    unchanged, not that the manuscript number is the number in the file.

    Returns
    -------
    dict
        ``success`` (False only when the check could not run), ``ok`` (no
        mismatches), ``mismatches`` / ``checked`` / ``unlocated`` lists.
    """
    try:
        project_path = resolve_project_path(project_dir).resolve()
        claims = _load_claims(project_path)["claims"]
        checked, mismatches, unlocated = [], [], []
        for claim_id, claim in claims.items():
            keys = claim.get("source_keys") or {}
            if not keys:
                unlocated.append(claim_id)
                continue
            source = resolve_output_file(project_path, claim.get("output_file"))
            for result in check_claim_against_source(
                claim.get("value"),
                str(source) if source else None,
                keys,
                claim.get("tolerance") or {},
            ):
                row = {"claim_id": claim_id, **result}
                (checked if result["ok"] else mismatches).append(row)
        return {
            "success": True,
            "ok": not mismatches,
            "checked": checked,
            "mismatches": mismatches,
            "unlocated": unlocated,
        }
    except Exception as e:
        return _failure(e)


def render_claims(project_dir: str) -> Dict:
    """Render all claims to 00_shared/claims_rendered.tex.

    This is called automatically before compilation when claims.json exists.
    Values are read from the scitex-clew store, never from the JSON file.
    The generated file defines the \\vclaim{id} LaTeX macro and all claim
    renderings for all styles.

    Parameters
    ----------
    project_dir : str
        Path to the scitex-writer project directory.

    Returns
    -------
    dict
        Success status and path to generated file.
    """
    try:
        project_path = resolve_project_path(project_dir)
        data = _load_claims(project_path)
        claims = data.get("claims", {})

        lines = [
            "%% Auto-generated by scitex-writer — do not edit manually.",
            f"%% Source: scitex-clew claim store (export: {CLAIMS_FILE})",
            "%% To update: run writer_claim_render or recompile the project.",
            "",
            "\\makeatletter",
            "",
            "%% \\vclaim[style]{id} — render a claim inline",
            "%% Note: #-tokens doubled to ## so this block survives being",
            "%% inlined inside another macro's body (e.g., the BODY position",
            "%% of \\IfFileExists{file}{BODY}{}). Single # also works at the",
            "%% top level, so ## is the portable choice.",
            "\\providecommand{\\vclaim}[2][nature]{%",
            "  \\expandafter\\ifx\\csname v@claim@##2@##1\\endcsname\\relax",
            "    [\\texttt{claim:##2}]%",
            "  \\else",
            "    \\v@claim@maybecolor{##2}{\\csname v@claim@##2@##1\\endcsname}%",
            "  \\fi}",
            "",
            "%% \\v@claim@maybecolor{id}{rendered} — clew provenance overlay.",
            "%% When the clew presentation markers layer is ACTIVE",
            "%% (\\ifclewpresmarkers, set by --clew-overlay / the master switch)",
            "%% AND this claim id has a clew color registered (clew@hex@<id>, emitted",
            "%% into clew_rendered.tex by render_clew using the SAME sanitize as the",
            "%% v@claim@ names, so keys align), wrap the rendered value in the",
            "%% verdict-colored decoration the clew layer uses (\\clewDecorate — the",
            "%% ulem \\uwave span). The value is \\mbox-wrapped first: the \\vclaim",
            '%% value macro bundles a \\hypertarget, and ulem \\uwave chokes ("Bad',
            '%% space factor (0)") on that box unless it is a single \\hbox; claim',
            "%% values are short single units, so this is safe. Falls back to the",
            "%% PLAIN rendered value (no \\mbox, no wave) in every",
            "%% other case, guarded by \\@ifundefined so a non-overlay compile (no",
            "%% clew_rendered.tex, markers off, or claim absent from the clew feed)",
            "%% never touches an undefined color/toggle macro.",
            "\\providecommand{\\v@claim@maybecolor}[2]{%",
            "  \\@ifundefined{clew@hex@##1}{##2}{%",
            "    \\@ifundefined{ifclewpresmarkers}{##2}{%",
            "      \\ifclewpresmarkers",
            "        \\begingroup",
            "        \\edef\\v@claim@clewhex{\\csname clew@hex@##1\\endcsname}%",
            "        \\definecolor{clewVerdict}{HTML}{\\v@claim@clewhex}%",
            "        \\clewDecorate{\\mbox{##2}}%",
            "        \\endgroup",
            "      \\else ##2\\fi}}%",
            "}",
            "",
        ]

        # Two claim IDs differing only in punctuation sanitise to the SAME macro
        # name, and \@namedef is \def -- the second definition silently replaces
        # the first, so both \vclaim calls render the LAST claim's value. That is
        # a wrong number in the manuscript, emitted by a renderer reporting
        # success. Refuse before writing rather than ship it.
        collisions = find_sanitize_collisions(claims.keys())
        if collisions:
            return {
                "success": False,
                "error": describe_sanitize_collisions(collisions),
            }

        if claims:
            lines.append("%% Rendered claims")
        else:
            lines.append("%% No claims defined yet.")

        for claim_id, claim in claims.items():
            safe_id = _sanitize_id(claim_id)
            context = claim.get("context", "")
            claim_type = claim.get("type", "unknown")
            lines.append(
                f"%% {claim_id} ({claim_type}){': ' + context if context else ''}"
            )
            # First rendering in the document creates a named PDF destination
            # via \hypertarget{vclaim-<id>}{…} — Living Paper (#133) uses this
            # so PDF.js can locate claim text for hover popups. Subsequent
            # calls don't re-emit the target (hyperref would warn on dup);
            # instead we use a one-shot flag per claim.
            flag = f"v@claim@{safe_id}@anchored"
            for style in FORMAT_STYLES:
                rendered = _render_claim(claim, style)
                macro_name = f"v@claim@{safe_id}@{style}"
                wrapped = (
                    f"\\expandafter\\ifx\\csname {flag}\\endcsname\\relax"
                    f"\\global\\@namedef{{{flag}}}{{}}"
                    f"\\hypertarget{{vclaim-{safe_id}}}{{{rendered}}}"
                    f"\\else {rendered}\\fi"
                )
                lines.append(f"\\@namedef{{{macro_name}}}{{{wrapped}}}")
            lines.append("")

        lines.append("\\makeatother")

        output_path = project_path / CLAIMS_RENDERED
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return {
            "success": True,
            "rendered_path": str(output_path),
            "claims_count": len(claims),
            "store": "scitex-clew",
            "notices": data["notices"],
        }
    except Exception as e:
        return _failure(e)


__all__ = [
    "CLAIM_TYPES",
    "FORMAT_STYLES",
    "add_claim",
    "list_claims",
    "get_claim",
    "remove_claim",
    "format_claim",
    "render_claims",
    "check_claim_values",
]

# EOF

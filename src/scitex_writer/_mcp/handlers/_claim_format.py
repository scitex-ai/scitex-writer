#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_claim_format.py

"""Claim → LaTeX-string formatting layer.

Pure, side-effect-free rendering helpers extracted from ``_claim.py`` (which
stays the CRUD + render-to-file orchestrator). Everything here maps a claim
dict to a LaTeX string for one of the FORMAT_STYLES; nothing here touches the
filesystem. Imported by ``_claim.py``; not part of the public MCP surface.
"""

import re
from typing import Dict

CLAIM_TYPES = ("statistic", "value", "citation", "figure", "table")
FORMAT_STYLES = ("nature", "apa", "plain")


def _sanitize_id(claim_id: str) -> str:
    """Sanitize claim ID for use in LaTeX macro names (letters only)."""
    return re.sub(r"[^a-zA-Z0-9]", "", claim_id)


def find_sanitize_collisions(claim_ids) -> Dict[str, list]:
    """Map each colliding macro name to the >1 claim_ids that collapse onto it.

    ``_sanitize_id`` strips every non-alphanumeric character, so ``group-a-effect``
    and ``group_a_effect`` both become ``groupaeffect`` -- the same LaTeX macro
    name. The renderer emits one ``\\@namedef`` per claim, and ``\\@namedef`` is
    ``\\def``: the second definition silently replaces the first. Both
    ``\\vclaim`` calls then expand to the LAST claim's value.

    That is a wrong NUMBER in a published manuscript, produced with no warning
    by a renderer reporting success. Two distinct claims must never share a
    macro, so any collision is a hard error -- there is no legitimate case.
    """
    groups: Dict[str, list] = {}
    for claim_id in claim_ids:
        groups.setdefault(_sanitize_id(claim_id), []).append(claim_id)
    return {safe: ids for safe, ids in groups.items() if len(ids) > 1}


def describe_sanitize_collisions(collisions: Dict[str, list]) -> str:
    """Name every colliding group, the value at stake, and the remedy."""
    lines = [
        "Claim IDs collide into the same LaTeX macro name.",
        "",
        "Macro names are built by stripping every non-alphanumeric character "
        "from the claim ID, so IDs differing only in punctuation produce the "
        "SAME macro. The later definition silently overwrites the earlier one, "
        "and every \\vclaim for the group then renders the LAST claim's value "
        "-- a wrong number in the manuscript, with no warning.",
        "",
    ]
    for safe, ids in sorted(collisions.items()):
        lines.append(f"  \\v@claim@{safe}@* <- {', '.join(sorted(ids))}")
    lines += [
        "",
        "Rename the claim IDs in 00_shared/claims.json so they differ by more "
        "than punctuation (letters and digits are what survive sanitisation).",
    ]
    return "\n".join(lines)


def _format_p(p: float, style: str) -> str:
    """Format a p-value according to style."""
    if p < 0.001:
        return "< 0.001" if style != "apa" else "< .001"
    fmt = f"{p:.3f}"
    return f"= {fmt}" if style != "apa" else f"= {fmt.lstrip('0')}"


def _format_statistic(value: Dict, style: str) -> str:
    """Format a statistic claim."""
    t = value.get("t")
    f = value.get("F")
    df = value.get("df")
    df1 = value.get("df1")
    df2 = value.get("df2")
    p = value.get("p")
    d = value.get("d")
    eta2 = value.get("eta2")
    r = value.get("r")

    parts = []

    if t is not None and df is not None:
        if style == "plain":
            parts.append(f"t({df}) = {t:.2f}")
        else:
            parts.append(f"$t({df}) = {t:.2f}$")
    elif f is not None and df1 is not None and df2 is not None:
        if style == "plain":
            parts.append(f"F({df1},{df2}) = {f:.2f}")
        else:
            parts.append(f"$F({df1},{df2}) = {f:.2f}$")
    elif r is not None:
        if style == "plain":
            parts.append(f"r = {r:.2f}")
        else:
            parts.append(f"$r = {r:.2f}$")

    if p is not None:
        p_str = _format_p(p, style)
        if style == "plain":
            parts.append(f"p {p_str}")
        else:
            parts.append(f"$p {p_str}$")

    if d is not None:
        if style == "apa":
            label = "Cohen's $d$"
            val_str = f"{d:.2f}"
            parts.append(f"{label} = {val_str}")
        elif style == "plain":
            parts.append(f"d = {d:.2f}")
        else:
            parts.append(f"$d = {d:.2f}$")
    elif eta2 is not None:
        if style == "plain":
            parts.append(f"eta2 = {eta2:.3f}")
        else:
            label = "$\\eta^2$" if style == "nature" else "$\\eta^2_p$"
            parts.append(f"{label} = {eta2:.3f}")

    return ", ".join(parts) if parts else str(value)


def _format_value(value: Dict, style: str) -> str:
    """Format a value claim.

    Supported shapes (checked in order):

    1. ``{"template_<style>": "...", ...}`` — per-style format string,
       rendered with ``template.format(**value)``. ``<style>`` is one of
       ``nature``, ``apa``, ``plain``. Lets a single claim carry three
       differently-typeset renderings (useful when math goes into
       ``$...$`` for nature/apa but stays plain for ``plain`` style).

    2. ``{"template": "...", ...}`` — single style-agnostic format
       string, rendered with ``template.format(**value)``. Takes the
       whole value dict as keyword args, so compound claims like
       ``{"n_sig": 73, "n_tot": 240, "frac": 0.304, ...}`` can pack a
       rich rendering into one claim ID without exploding the JSON into
       atomic sub-claims.

    3. ``{"value": X, "unit": Y}`` (legacy single-value shape) — renders
       as ``X Y`` (plain) or ``$X$ Y`` (nature/apa). Unit optional.

    4. Any other dict — falls back to ``key=val, key=val, ...`` so the
       claim is at least visible in the rendered tex and users can spot
       that they need to add a ``template``.

    Parameters
    ----------
    value : dict
        The claim's value payload.
    style : str
        One of the FORMAT_STYLES constants (nature, apa, plain).
    """
    if not isinstance(value, dict):
        return str(value)

    # (1) per-style template
    per_style = value.get(f"template_{style}")
    if isinstance(per_style, str):
        try:
            return per_style.format(**value)
        except (KeyError, IndexError, ValueError):
            pass

    # (2) single shared template
    template = value.get("template")
    if isinstance(template, str):
        try:
            return template.format(**value)
        except (KeyError, IndexError, ValueError):
            pass

    # (3) legacy single-value shape
    if "value" in value:
        v = _latex_escape_value(value.get("value", ""))
        unit = _latex_escape_value(value.get("unit", ""))
        if unit:
            return f"{v} {unit}" if style == "plain" else f"${v}$ {unit}"
        return str(v)

    # (4) fallback — flat key=val dump
    return ", ".join(
        f"{k}={_latex_escape_value(v)}"
        for k, v in value.items()
        if not (isinstance(k, str) and k.startswith("template"))
    )


def _format_citation(value: Dict, style: str) -> str:
    """Format a citation claim — just returns user-supplied text."""
    return _latex_escape_value(value.get("text", ""))


def _format_figure(value: Dict, style: str) -> str:
    """Format a figure reference."""
    label = value.get("label", "")
    return f"\\ref{{{label}}}"


def _format_table(value: Dict, style: str) -> str:
    """Format a table reference."""
    label = value.get("label", "")
    return f"\\ref{{{label}}}"


def _latex_escape_value(s: str) -> str:
    """Escape LaTeX special characters in a claim value string.

    Only the silent-killer specials (`%`, unbalanced `{` / `}`, `&`, `#`,
    `$`, `_`) are escaped — characters that template-authors might use
    intentionally (`\\`, `^`, `~`) are left alone. The motivating bug:
    a claim value of `"25%"` (e.g. bix-6 q5 percentage) was inlined raw
    into LaTeX, where `%` starts a comment that consumed the closing
    brace of the surrounding `\\IfFileExists{file}{BODY}` wrapper and
    triggered a runaway-argument error on every compile. Discovered
    2026-05-03 in paper-scitex-clew."""
    if not isinstance(s, str):
        s = str(s)
    return (
        s.replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("#", "\\#")
        .replace("_", "\\_")
    )


def _render_claim(claim: Dict, style: str) -> str:
    """Render a single claim as a LaTeX string."""
    claim_type = claim.get("type", "value")
    value = claim.get("value", {})
    if isinstance(value, str):
        return _latex_escape_value(value)
    formatters = {
        "statistic": _format_statistic,
        "value": _format_value,
        "citation": _format_citation,
        "figure": _format_figure,
        "table": _format_table,
    }
    fn = formatters.get(claim_type, _format_value)
    return fn(value, style)


__all__ = [
    "CLAIM_TYPES",
    "FORMAT_STYLES",
    "_sanitize_id",
    "find_sanitize_collisions",
    "describe_sanitize_collisions",
    "_format_p",
    "_format_statistic",
    "_format_value",
    "_format_citation",
    "_format_figure",
    "_format_table",
    "_latex_escape_value",
    "_render_claim",
]

# EOF

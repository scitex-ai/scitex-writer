#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/claim.py

"""Claim functions for traceable scientific assertions in manuscripts.

Usage::

    import scitex_writer as sw

    # Add a statistical claim
    sw.claim.add(
        "./my-paper", "group_comparison", "statistic",
        {"t": 4.23, "df": 34, "p": 0.00032, "d": 0.87},
        context="Group A vs B alpha power comparison",
    )

    # List all claims
    sw.claim.list("./my-paper")

    # Format for inline display
    sw.claim.format("./my-paper", "group_comparison", style="apa")

    # Render to LaTeX (auto-called before compile)
    sw.claim.render("./my-paper")

Storage: every claim is registered in the scitex-clew store (the single
source of truth, so each \\vclaim back-traces through clew's DAG to the run
that produced it); ``00_shared/claims.json`` is a derived export. Without
scitex-clew or a reachable store every call returns ``success: False`` with
``error_kind: "clew_unavailable"`` -- there is no local-JSON fallback.

Value-vs-source (checked before every compile)::

    sw.claim.add(
        "./my-paper", "auc", "value", {"value": 0.91},
        output_file="results/metrics.json",
        source_keys={"value": {"pointer": "/test/auc"}},   # RFC 6901
    )
    sw.claim.check_values("./my-paper")

In LaTeX (after render):
    \\vclaim{group_comparison}           % nature style: t(34) = 4.23, p < 0.001, d = 0.87
    \\vclaim[apa]{group_comparison}      % APA style:    t(34) = 4.23, p < .001, Cohen's d = 0.87
    \\vclaim[plain]{group_comparison}    % plain text:   t(34) = 4.23, p < 0.001, d = 0.87
"""

from ._mcp.handlers._claim import add_claim as _add_claim
from ._mcp.handlers._claim import check_claim_values as _check_claim_values
from ._mcp.handlers._claim import format_claim as _format_claim
from ._mcp.handlers._claim import get_claim as _get_claim
from ._mcp.handlers._claim import list_claims as _list_claims
from ._mcp.handlers._claim import remove_claim as _remove_claim
from ._mcp.handlers._claim import render_claims as _render_claims


def add(
    project_dir,
    claim_id,
    claim_type,
    value,
    context=None,
    session_id=None,
    output_file=None,
    output_hash=None,
    test=None,
    source_keys=None,
    tolerance=None,
    tex_file=None,
    line_number=None,
):
    """Register (or update) a claim in the scitex-clew store.

    See :func:`scitex_writer._mcp.handlers._claim.add_claim` for parameters
    (``source_keys`` / ``tolerance`` drive the value-vs-source check).
    """
    return _add_claim(
        project_dir,
        claim_id,
        claim_type,
        value,
        context,
        session_id,
        output_file,
        output_hash,
        test,
        source_keys=source_keys,
        tolerance=tolerance,
        tex_file=tex_file,
        line_number=line_number,
    )


def list(project_dir):  # noqa: A001
    """List all claims in the project."""
    return _list_claims(project_dir)


def get(project_dir, claim_id):
    """Get full details of a specific claim."""
    return _get_claim(project_dir, claim_id)


def remove(project_dir, claim_id):
    """Retire a claim (clew supersede) and refresh the derived export."""
    return _remove_claim(project_dir, claim_id)


def format(project_dir, claim_id, style="nature"):  # noqa: A001
    """Render a claim as a formatted LaTeX string."""
    return _format_claim(project_dir, claim_id, style)


def render(project_dir):
    """Generate 00_shared/claims_rendered.tex from the clew claim store."""
    return _render_claims(project_dir)


def check_values(project_dir):
    """Re-read located claim values from their sources and compare."""
    return _check_claim_values(project_dir)


__all__ = ["add", "list", "get", "remove", "format", "render", "check_values"]

# EOF

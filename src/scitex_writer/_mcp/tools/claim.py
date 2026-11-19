#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/tools/claim.py

"""Claim MCP tools — traceable scientific assertions in LaTeX manuscripts."""

from typing import Any, Dict, Optional

from fastmcp import FastMCP

from ..handlers._claim import (
    add_claim as _add_claim,
)
from ..handlers._claim import (
    check_claim_values as _check_claim_values,
)
from ..handlers._claim import (
    format_claim as _format_claim,
)
from ..handlers._claim import (
    get_claim as _get_claim,
)
from ..handlers._claim import (
    list_claims as _list_claims,
)
from ..handlers._claim import (
    remove_claim as _remove_claim,
)
from ..handlers._claim import (
    render_claims as _render_claims,
)


def register_tools(mcp: FastMCP) -> None:
    """Register claim tools with the MCP server."""

    @mcp.tool()
    def writer_claim_add(
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
    ) -> dict:
        """Register (or update) a claim in the scitex-clew claim store.

        Claims are traceable scientific assertions — statistics, values, citations —
        stored as structured objects instead of hardcoded magic numbers. The
        scitex-clew store is the single source of truth (00_shared/claims.json
        is a derived export); output_file/session_id link the claim into
        clew's provenance DAG. Fails (success=False, error_kind=
        "clew_unavailable") when clew or its store is unreachable — no fallback.

        source_keys makes the value checkable against its source before every
        compile: {"<value field>": locator}, locator = {"pointer": "/a/0/b"}
        for json/yaml (RFC 6901) or {"row": 3 | {"col": "val"}, "column":
        "name"} for csv/tsv; optional abs_tol/rel_tol per locator or via
        tolerance={"abs_tol": .., "rel_tol": ..}. Undeclared tolerance = the
        precision the value is written with (0.91 -> +-0.005). A claim that
        already disagrees with its source is refused.

        After adding claims, use writer_claim_render (or recompile) to generate
        the LaTeX macro file. Then use \\vclaim{claim_id} in your manuscript.

        claim_type options:
          - statistic: value={t, df, p, d} or {F, df1, df2, p, eta2} or {r, p}
          - value: value={value, unit}
          - citation: value={text}
          - figure: value={label}
          - table: value={label}

        Examples:
          writer_claim_add("./paper", "group_comparison", "statistic",
                           {"t": 4.23, "df": 34, "p": 0.00032, "d": 0.87},
                           context="Group A vs B alpha power")
          writer_claim_add("./paper", "replic_rate", "citation",
                           {"text": "70\\\\%"}, context="Baker 2016 replication")
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

    @mcp.tool()
    def writer_claim_check_values(project_dir: str) -> dict:
        """Re-read every located claim value from its source file and compare.

        Reports claims whose value disagrees with the value at their
        source_keys locator (beyond tolerance) as mismatches.
        """
        return _check_claim_values(project_dir)

    @mcp.tool()
    def writer_claim_list(project_dir: str) -> dict:
        """List all claims in the project.

        Returns each claim's ID, type, context, and a nature-style preview.
        """
        return _list_claims(project_dir)

    @mcp.tool()
    def writer_claim_get(project_dir: str, claim_id: str) -> dict:
        """Get full details of a specific claim including all style renderings.

        Returns the raw claim data and rendered previews for nature, apa, and plain styles.
        """
        return _get_claim(project_dir, claim_id)

    @mcp.tool()
    def writer_claim_remove(project_dir: str, claim_id: str) -> dict:
        """Retire a claim from the clew store (supersede; kept for audit).

        Note: Re-run writer_claim_render after removal to update claims_rendered.tex.
        """
        return _remove_claim(project_dir, claim_id)

    @mcp.tool()
    def writer_claim_format(
        project_dir: str,
        claim_id: str,
        style: str = "nature",
    ) -> dict:
        """Render a claim as a formatted LaTeX string.

        style options:
          - nature: p < 0.001, standard journal format (default)
          - apa: p < .001, APA Publication Manual format
          - plain: plain text without LaTeX math delimiters
        """
        return _format_claim(project_dir, claim_id, style)

    @mcp.tool()
    def writer_claim_render(project_dir: str) -> dict:
        """Generate 00_shared/claims_rendered.tex from the clew claim store.

        This file defines the \\vclaim[style]{id} LaTeX macro and all claim
        renderings. It is included automatically in the manuscript preamble
        (via \\IfFileExists in packages.tex) and is regenerated before each compile.

        Run this explicitly after modifying claims to update the rendered file
        without a full recompilation.
        """
        return _render_claims(project_dir)


# EOF

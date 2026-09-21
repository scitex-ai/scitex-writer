#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim handlers — Django port of the Flask `_routes_claim` module.

The underlying logic (`add_claim`, `get_claim`, …) lives in
`scitex_writer._mcp.handlers._claim` and is framework-agnostic; these
handlers are thin Django wrappers that parse the request and serialize
the response.
"""

from __future__ import annotations

import json

from scitex_logging import getLogger

from django.http import JsonResponse

logger = getLogger(__name__)


def _parse_json(request) -> dict:
    try:
        return json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return {}


def handle_list_claims(request, project):
    from ..._mcp.handlers._claim import list_claims

    return JsonResponse(list_claims(str(project.project_dir)))


def handle_get_claim(request, project, claim_id: str):
    from ..._mcp.handlers._claim import get_claim

    return JsonResponse(get_claim(str(project.project_dir), claim_id))


def handle_add_claim(request, project):
    from ..._mcp.handlers._claim import add_claim

    data = _parse_json(request)
    required = {"claim_id", "claim_type", "value"}
    missing = required - data.keys()
    if missing:
        return JsonResponse(
            {"success": False, "error": f"Missing fields: {missing}"}, status=400
        )
    return JsonResponse(
        add_claim(
            str(project.project_dir),
            claim_id=data["claim_id"],
            claim_type=data["claim_type"],
            value=data["value"],
            context=data.get("context"),
            session_id=data.get("session_id"),
            output_file=data.get("output_file"),
            output_hash=data.get("output_hash"),
            test=data.get("test"),
        )
    )


def handle_remove_claim(request, project, claim_id: str):
    from ..._mcp.handlers._claim import remove_claim

    return JsonResponse(remove_claim(str(project.project_dir), claim_id))


def handle_claim_chain(request, project, claim_id: str):
    from pathlib import Path

    from ..._mcp.handlers._claim import (
        _dangling_output_error,
        _output_file_exists,
        get_claim,
    )

    claim_result = get_claim(str(project.project_dir), claim_id)
    if not claim_result.get("success"):
        return JsonResponse(claim_result)

    claim = claim_result["claim"]
    output_file = claim.get("output_file")
    session_id = claim.get("session_id")
    # A recorded pointer to a file that is NOT THERE is not provenance. This was
    # `bool(output_file or session_id)` — true for any non-empty string — so a
    # claim whose output was deleted or never written still reported provenance
    # it did not have.
    output_exists = _output_file_exists(Path(project.project_dir), output_file)
    response = {
        "success": True,
        "claim_id": claim_id,
        "claim": claim,
        "previews": claim_result.get("previews", {}),
        "mermaid": None,
        "clew_available": False,
        "output_file_exists": output_exists,
        "has_provenance": bool(session_id or output_exists),
        "provenance_error": _dangling_output_error(output_file, output_exists),
    }
    if output_file or session_id:
        try:
            from scitex_clew import generate_mermaid_dag
        except ImportError:
            response["clew_available"] = False
        else:
            response["clew_available"] = True
            kwargs = {}
            if output_file:
                kwargs["target_file"] = output_file
            elif session_id:
                kwargs["session_id"] = session_id
            try:
                response["mermaid"] = generate_mermaid_dag(**kwargs)
            except Exception as exc:
                # This was `except Exception: pass`, so a failing DAG left
                # clew_available=True and mermaid=None — the pane reported Clew
                # as working and simply drew nothing, with no way to find out
                # why. Say what broke.
                logger.warning("[claim] Clew DAG failed for %s: %s", claim_id, exc)
                response["mermaid_error"] = str(exc)

    return JsonResponse(response)


def handle_render_claims(request, project):
    from ..._mcp.handlers._claim import render_claims

    return JsonResponse(render_claims(str(project.project_dir)))

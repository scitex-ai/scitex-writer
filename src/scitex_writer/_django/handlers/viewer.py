#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Viewer handlers — claims metadata sidecar, DAG, citation verification.

Backs the live-paper viewer (issue #82 / cloud #133):
- GET /api/claims-metadata — claims.json + per-claim verification state
- GET /api/dag?target=…    — Clew DAG as Mermaid code
- GET /api/citation/<key>  — scitex-scholar verification state
"""

from __future__ import annotations

import importlib.util

from scitex_logging import getLogger

from django.http import JsonResponse

logger = getLogger(__name__)

# Verification states mirrored from scitex-scholar's schema.
_CITATION_VERIFIED = "VERIFIED"
_CITATION_UNVERIFIABLE = "UNVERIFIABLE"
_CITATION_CONTRADICTED = "CONTRADICTED"


def handle_claims_metadata(request, project):
    """Return all claims with verification state (clew-aware if available)."""
    from ..._mcp.handlers._claim import list_claims

    result = list_claims(str(project.project_dir))
    if not result.get("success"):
        return JsonResponse(result, status=500)

    # Augment each claim with its Clew verification state if available.
    for claim in result.get("claims", []):
        claim["verification"] = _claim_verification_state(project, claim)

    return JsonResponse(result)


def handle_dag(request, project):
    """Return Mermaid DAG code for a target file or session."""
    target_file = request.GET.get("target")
    session_id = request.GET.get("session")
    claim_id = request.GET.get("claim")

    if claim_id:
        from ..._mcp.handlers._claim import get_claim

        claim_result = get_claim(str(project.project_dir), claim_id)
        if not claim_result.get("success"):
            return JsonResponse(claim_result, status=404)
        claim = claim_result["claim"]
        target_file = target_file or claim.get("output_file")
        session_id = session_id or claim.get("session_id")

    if not target_file and not session_id:
        return JsonResponse(
            {
                "success": False,
                "error": "Pass ?target=<file>, ?session=<id>, or ?claim=<id>",
            },
            status=400,
        )

    try:
        from scitex_clew import generate_mermaid_dag

        kwargs: dict = {}
        if target_file:
            kwargs["target_file"] = target_file
        elif session_id:
            kwargs["session_id"] = session_id
        mermaid = generate_mermaid_dag(**kwargs)
        return JsonResponse(
            {
                "success": True,
                "target_file": target_file,
                "session_id": session_id,
                "mermaid": mermaid,
            }
        )
    except ImportError:
        return JsonResponse(
            {"success": False, "error": "scitex-clew not installed"},
            status=501,
        )
    except Exception as exc:
        logger.exception("[viewer] DAG generation failed")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _citation_unavailable_reason() -> str:
    """Why citation verification is unavailable, stated accurately.

    An ``except ImportError`` here answered BOTH failures with "scitex-scholar
    not installed", and only one of them is that. Measured 2026-08-18 against
    scholar 1.7.1: ``verify_citation`` DOES NOT EXIST — no such symbol
    anywhere in the package, and nothing obviously equivalent among its public
    names. So every citation in the live-paper viewer has been coming back
    UNVERIFIABLE with a reason that is false, on a machine where scholar is
    installed and working.

    That is the same shape as the 2.30.2 NO_PROVENANCE defect: a verification
    surface reporting "could not check" for a reason that sends the reader to
    fix something already fine. On a provenance tool that is a wrong answer
    about the science, not a UI wart.
    """
    if importlib.util.find_spec("scitex_scholar") is None:
        return "scitex-scholar is not installed"
    return (
        "scitex-scholar is installed but no longer exposes verify_citation, "
        "so citations cannot be checked; this is a missing upstream "
        "capability, not a problem with this manuscript or its bibliography"
    )


def handle_citation(request, project, cite_key: str):
    """Return verification state for a bibliography citation key.

    Consumes scitex-scholar when available; degrades to UNVERIFIABLE with an
    ACCURATE reason otherwise, so the frontend can show a consistent badge and
    the reader is not sent to debug the wrong thing.
    """
    try:
        from scitex_scholar import verify_citation  # type: ignore

        state = verify_citation(str(project.project_dir), cite_key)
        return JsonResponse({"success": True, "cite_key": cite_key, **state})
    except ImportError:
        return JsonResponse(
            {
                "success": True,
                "cite_key": cite_key,
                "state": _CITATION_UNVERIFIABLE,
                "reason": _citation_unavailable_reason(),
            }
        )
    except Exception as exc:
        logger.exception("[viewer] citation %s", cite_key)
        return JsonResponse(
            {"success": False, "cite_key": cite_key, "error": str(exc)},
            status=500,
        )


def _claim_verification_state(project, claim: dict) -> dict:
    """Verify a claim through Clew's own per-claim entry point.

    This used to hand-roll the verdict out of ``verify_chain(target_file=...)``.
    No published Clew has ever had a ``target_file`` parameter — ``verify_chain``
    takes a single positional ``target`` — and it has no ``session_id`` parameter
    either, so BOTH branches raised TypeError on every call. The exception was
    logged at DEBUG and returned as a per-claim state of ``"ERROR"``, which reads
    as "this claim could not be verified" when the truth was "writer called Clew
    wrong". A wiring bug wearing the costume of a data problem: it shipped, and
    verified zero of the 40 claims in a real manuscript.

    Clew ships ``verify_claim`` for exactly this, and returns its OWN reasons in
    ``details`` — better than any verdict we could synthesise.
    """
    claim_id = claim.get("claim_id")
    output_file = claim.get("output_file")
    session_id = claim.get("session_id")
    if not (output_file or session_id):
        return {"state": "NO_PROVENANCE"}

    try:
        from scitex_clew import verify_chain, verify_claim
    except ImportError:
        return {"state": "CLEW_MISSING"}

    try:
        if claim_id:
            verdict = verify_claim(claim_id)
            return {
                "state": "VERIFIED" if verdict.get("chain_verified") else "UNVERIFIED",
                "source_verified": verdict.get("source_verified"),
                "chain_verified": verdict.get("chain_verified"),
                # Clew's reasons, carried through. Without them the pane can say
                # a claim failed but never say why.
                "details": verdict.get("details") or [],
                "output_file": output_file,
                "session_id": session_id,
            }
        if output_file:
            status = verify_chain(output_file)
            return {
                "state": (
                    status.status.name if hasattr(status, "status") else str(status)
                ),
                "output_file": output_file,
                "session_id": session_id,
            }
        # A session id alone gives Clew nothing to chase: neither entry point
        # accepts one. Say so, rather than reporting a verification we did not
        # perform.
        return {"state": "UNVERIFIABLE_NO_TARGET", "session_id": session_id}
    except TypeError:
        # A TypeError here is OUR call being wrong, not a fact about the claim.
        # Reporting it as a per-claim "ERROR" is precisely how the previous bug
        # stayed invisible across two releases. Let it out.
        raise
    except Exception as exc:
        logger.warning(
            "[viewer] Clew verification failed for %s: %s",
            claim_id or output_file,
            exc,
        )
        return {"state": "ERROR", "error": str(exc)}

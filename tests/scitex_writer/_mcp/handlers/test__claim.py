#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: src/scitex_writer/_mcp/handlers/_claim.py

"""`list_claims` must carry a claim's provenance POINTERS, not just a boolean.

Why this file exists: `list_claims` computed `has_provenance` from a claim's
`session_id` / `output_file` and then DROPPED both fields from the projection it
returned. The live-paper viewer verifies each claim's chain by passing those
pointers to `scitex_clew.verify_chain` — so with nothing to pass, every claim
came back `NO_PROVENANCE`, including the claims that HAD provenance and would
have verified. A wrong answer, delivered confidently, with no error anywhere.

That is the same failure shape as the silent port slide and the silent editor
downgrade: a degraded result presented as a real one. `has_provenance: true`
with no pointers is not a summary, it is a dead end.
"""

import json

import pytest

from scitex_writer._mcp.handlers._claim import list_claims

# Claims are stored in scitex-clew (the one claim store): every test here
# needs the real store, on a throwaway schema.
pytestmark = pytest.mark.usefixtures("clew_store")


def _project_with_claims(tmp_path, claims: dict):
    """A real project tree with a real 00_shared/claims.json."""
    shared = tmp_path / "00_shared"
    shared.mkdir(parents=True)
    (shared / "claims.json").write_text(json.dumps({"claims": claims}))
    return tmp_path


def _claim_named(result, claim_id):
    return next(c for c in result["claims"] if c["claim_id"] == claim_id)


CLAIM_WITH_BOTH = {
    "type": "value",
    "context": "accuracy",
    "value": "0.91",
    "session_id": "sess-2026-07-13",
    "output_file": "scripts/eval/out/accuracy.json",
}
CLAIM_WITH_NEITHER = {"type": "value", "context": "hand-typed", "value": "42"}


def test_list_claims_carries_the_output_file_pointer(tmp_path):
    # Arrange
    project = _project_with_claims(tmp_path, {"acc": CLAIM_WITH_BOTH})
    # Act
    result = list_claims(str(project))
    # Assert
    assert _claim_named(result, "acc")["output_file"] == (
        "scripts/eval/out/accuracy.json"
    )


def test_list_claims_carries_the_session_id_pointer(tmp_path):
    # Arrange
    project = _project_with_claims(tmp_path, {"acc": CLAIM_WITH_BOTH})
    # Act
    result = list_claims(str(project))
    # Assert
    assert _claim_named(result, "acc")["session_id"] == "sess-2026-07-13"


def test_list_claims_still_reports_has_provenance_true(tmp_path):
    # Arrange
    project = _project_with_claims(tmp_path, {"acc": CLAIM_WITH_BOTH})
    # Act
    result = list_claims(str(project))
    # Assert
    assert _claim_named(result, "acc")["has_provenance"] is True


def test_list_claims_reports_has_provenance_false_without_pointers(tmp_path):
    # Arrange
    project = _project_with_claims(tmp_path, {"bare": CLAIM_WITH_NEITHER})
    # Act
    result = list_claims(str(project))
    # Assert
    assert _claim_named(result, "bare")["has_provenance"] is False


def test_list_claims_leaves_pointers_none_when_the_claim_has_none(tmp_path):
    # Arrange
    project = _project_with_claims(tmp_path, {"bare": CLAIM_WITH_NEITHER})
    # Act
    result = list_claims(str(project))
    # Assert
    assert _claim_named(result, "bare")["output_file"] is None

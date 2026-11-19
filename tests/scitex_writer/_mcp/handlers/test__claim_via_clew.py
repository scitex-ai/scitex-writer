#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: src/scitex_writer/_mcp/handlers/_claim.py (+ _claim_store.py)

"""Writer's claims go THROUGH scitex-clew: one store, no silent fallback.

Before: ``add_claim`` wrote its own ``00_shared/claims.json`` and never called
``scitex_clew.add_claim``, so a manuscript had two claim stores and a
``\\vclaim`` could not be traced through clew's DAG. These tests pin:

* registration lands in the REAL clew store (queried through clew's own API);
* ``claims.json`` is only a derived export; a legacy one is migrated, loudly;
* with no reachable store every call FAILS, and nothing is read from or
  written to the JSON file as a substitute;
* remove + re-add round-trips (writer supersedes; re-registering reactivates);
* writer's fields use clew's native columns (display / value / source_keys /
  tolerance / metadata), so ``clew verify`` itself checks located values,
  and rows written as the older JSON envelope are still read;
* every clew call is scoped by ``project_root``, never by the cwd.

Real files, real PostgreSQL schema (``clew_store``), no mocks.
"""

import json
import os
import warnings
from pathlib import Path

import pytest

from scitex_writer._mcp.handlers._claim import (
    add_claim,
    get_claim,
    list_claims,
    remove_claim,
    render_claims,
)
from scitex_writer._mcp.handlers._claim_store import (
    DERIVED_MARKER,
    ENVELOPE_SCHEMA,
    METADATA_SCHEMA,
)


def _project(tmp_path: Path, name: str = "paper") -> Path:
    project = tmp_path / name
    (project / "00_shared").mkdir(parents=True)
    contents = project / "01_manuscript" / "contents"
    contents.mkdir(parents=True)
    (contents / "results.tex").write_text(
        "% \\vclaim{acc} in a comment is not a call site\n"
        "Accuracy reached \\vclaim{acc} on the test set.\n",
        encoding="utf-8",
    )
    (project / "data").mkdir()
    (project / "data" / "metrics.json").write_text(
        json.dumps({"test": {"acc": 0.9134}}), encoding="utf-8"
    )
    return project


def _clew_rows(project: Path):
    """The claims as CLEW reports them — not via any writer code path."""
    import scitex_clew

    return {
        c.claim_id: c
        for c in scitex_clew.list_claims(
            file_path_prefix=str(project.resolve()), project_root=str(project)
        )
    }


def _clew_rows_at(scope: Path, project: Path):
    """The project's claims as clew lists them in the scope of ``scope``."""
    import scitex_clew

    return {
        c.claim_id: c
        for c in scitex_clew.list_claims(
            file_path_prefix=str(project.resolve()), project_root=str(scope)
        )
    }


def _clew_verify(project: Path, claim_id: str) -> dict:
    """clew's own verdict on one claim (clew's verify, not writer's check)."""
    import scitex_clew

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return scitex_clew.verify_claim(claim_id, project_root=str(project))


# ---------------------------------------------------------------------------
# Registration goes through clew
# ---------------------------------------------------------------------------


class TestRegistrationThroughClew:
    def test_add_claim_lands_in_the_clew_store(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)

        # Act
        result = add_claim(
            str(project),
            "acc",
            "value",
            {"value": 0.91},
            output_file="data/metrics.json",
        )

        # Assert
        assert (result["success"], "acc" in _clew_rows(project)) == (True, True)

    def test_clew_row_carries_source_file_hash_and_location(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)

        # Act
        add_claim(
            str(project),
            "acc",
            "value",
            {"value": 0.91},
            output_file="data/metrics.json",
        )
        row = _clew_rows(project)["acc"]

        # Assert: back-traceable — source file + its hash + manuscript line
        assert (
            Path(row.source_file) == (project / "data" / "metrics.json").resolve(),
            row.source_hash is not None,
            Path(row.file_path).name,
            row.line_number,
        ) == (True, True, "results.tex", 2)

    def test_claim_value_is_only_the_display_string(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)

        # Act
        add_claim(str(project), "acc", "value", {"value": 0.91}, context="test acc")
        row = _clew_rows(project)["acc"]

        # Assert: no JSON packed into clew's display column any more
        assert row.claim_value == "0.91"

    def test_writer_fields_travel_in_clews_metadata(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)

        # Act
        add_claim(str(project), "acc", "value", {"value": 0.91}, context="test acc")
        metadata = _clew_rows(project)["acc"].metadata

        # Assert
        assert (metadata["schema"], metadata["value"], metadata["context"]) == (
            METADATA_SCHEMA,
            {"value": 0.91},
            "test acc",
        )

    def test_locator_and_tolerance_use_clews_native_columns(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)
        locator = {"value": {"pointer": "/test/acc"}}

        # Act
        add_claim(
            str(project),
            "acc",
            "value",
            {"value": 0.9134, "unit": "%"},
            output_file="data/metrics.json",
            source_keys=locator,
            tolerance={"abs_tol": 0.001},
        )
        row = _clew_rows(project)["acc"]

        # Assert: clew's value = the LOCATED field only (unit is render data)
        assert (row.value, row.source_keys, row.tolerance) == (
            {"value": 0.9134},
            locator,
            {"abs_tol": 0.001},
        )

    def test_clews_own_verify_reads_the_located_value(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)
        add_claim(
            str(project),
            "acc",
            "value",
            {"value": 0.9134},
            output_file="data/metrics.json",
            source_keys={"value": {"pointer": "/test/acc"}},
        )

        # Act
        result = _clew_verify(project, "acc")

        # Assert: clew itself (not writer) re-read /test/acc and compared it
        assert [(c["field"], c["ok"]) for c in result["value_checks"]] == [
            ("text/value", True),
            ("value", True),
        ]

    def test_statistic_with_p_below_bound_verifies_in_clew(self, tmp_path, clew_store):
        # Arrange: rendered "p < 0.001" for p = 0.0002 must not read as 0.001
        project = _project(tmp_path)
        (project / "data" / "stats.json").write_text(
            json.dumps({"t": 5.123, "df": 28, "p": 0.0002}), encoding="utf-8"
        )
        add_claim(
            str(project),
            "ttest",
            "statistic",
            {"t": 5.123, "df": 28, "p": 0.0002},
            output_file="data/stats.json",
            source_keys={"t": "/t", "p": "/p"},
        )

        # Act
        result = _clew_verify(project, "ttest")

        # Assert
        assert all(c["ok"] for c in result["value_checks"]), result["details"]

    def test_legacy_envelope_rows_are_still_read(self, tmp_path, clew_store):
        # Arrange: a row as writer registered it before the native columns
        import scitex_clew

        project = _project(tmp_path)
        envelope = {
            "schema": ENVELOPE_SCHEMA,
            "display": "0.91",
            "type": "value",
            "value": {"value": 0.91},
            "context": "old acc",
        }
        scitex_clew.add_claim(
            file_path=str(project / "00_shared" / "claims.json"),
            claim_type="value",
            claim_value=json.dumps(envelope),
            claim_id="acc",
            project_root=str(project),
        )

        # Act
        claim = get_claim(str(project), "acc")["claim"]

        # Assert
        assert (claim["value"], claim["context"]) == ({"value": 0.91}, "old acc")

    def test_registration_never_changes_the_working_directory(
        self, tmp_path, clew_store
    ):
        # Arrange: run from somewhere that is NOT the project
        project = _project(tmp_path)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        previous = os.getcwd()
        os.chdir(elsewhere)
        try:
            # Act
            add_claim(str(project), "acc", "value", {"value": 0.91})
            cwd_after = Path.cwd()
        finally:
            os.chdir(previous)

        # Assert: scoped to the project by project_root, not by the cwd
        assert (cwd_after, "acc" in _clew_rows(project)) == (elsewhere, True)

    def test_workspace_shares_the_research_projects_clew_scope(
        self, tmp_path, clew_store
    ):
        # Arrange: create-project puts the workspace at <root>/.scitex/writer,
        # a template clone carrying its OWN .git and pyproject.toml; its claims
        # still belong with the runs of <root>.
        root = tmp_path / "study"
        root.mkdir()
        (root / "pyproject.toml").write_text("[project]\nname = 'study'\n")
        workspace = _project(root / ".scitex", name="writer")
        (workspace / ".git").mkdir()
        (workspace / "pyproject.toml").write_text("[project]\nname = 'tmpl'\n")

        # Act
        add_claim(str(workspace), "acc", "value", {"value": 0.91})

        # Assert: visible in the research root's scope, not only the workspace's
        assert (
            "acc" in _clew_rows_at(root, workspace),
            "acc" in _clew_rows_at(workspace, workspace),
        ) == (True, False)

    def test_claims_json_is_a_derived_export(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)

        # Act
        add_claim(str(project), "acc", "value", {"value": 0.91})
        export = json.loads((project / "00_shared" / "claims.json").read_text())

        # Assert
        assert (export["_derived_from"], list(export["claims"])) == (
            DERIVED_MARKER,
            ["acc"],
        )

    def test_render_reads_values_from_the_store(self, tmp_path, clew_store):
        # Arrange: register, then vandalise the export — the store must win.
        project = _project(tmp_path)
        add_claim(str(project), "acc", "value", {"value": 0.91})
        export_path = project / "00_shared" / "claims.json"
        export = json.loads(export_path.read_text())
        export["claims"]["acc"]["value"] = {"value": 0.11}
        export_path.write_text(json.dumps(export))

        # Act
        render_claims(str(project))
        rendered = (project / "00_shared" / "claims_rendered.tex").read_text()

        # Assert
        assert ("0.91" in rendered, "0.11" in rendered) == (True, False)

    def test_remove_then_re_add_is_visible_again(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)
        add_claim(str(project), "acc", "value", {"value": 0.91})
        remove_claim(str(project), "acc")

        # Act
        add_claim(str(project), "acc", "value", {"value": 0.92})

        # Assert
        assert get_claim(str(project), "acc")["claim"]["value"] == {"value": 0.92}

    def test_removed_claim_leaves_the_export(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)
        add_claim(str(project), "acc", "value", {"value": 0.91})

        # Act
        remove_claim(str(project), "acc")
        export = json.loads((project / "00_shared" / "claims.json").read_text())

        # Assert
        assert export["claims"] == {}

    def test_stale_output_hash_is_refused(self, tmp_path, clew_store):
        # Arrange: the value was computed from a DIFFERENT version of the file
        project = _project(tmp_path)

        # Act
        result = add_claim(
            str(project),
            "acc",
            "value",
            {"value": 0.91},
            output_file="data/metrics.json",
            output_hash="0" * 64,
        )

        # Assert
        assert (result["success"], "output_hash" in result["error"]) == (False, True)


# ---------------------------------------------------------------------------
# Legacy claims.json: migrated on read, loudly
# ---------------------------------------------------------------------------


LEGACY = {
    "version": "1.0",
    "claims": {
        "n_subjects": {"type": "value", "value": {"value": 42}, "context": "N"},
    },
}


class TestLegacyMigration:
    def _legacy_project(self, tmp_path):
        project = _project(tmp_path)
        (project / "00_shared" / "claims.json").write_text(json.dumps(LEGACY))
        return project

    def test_legacy_claims_are_registered_in_clew(self, tmp_path, clew_store):
        # Arrange
        project = self._legacy_project(tmp_path)

        # Act
        list_claims(str(project))

        # Assert
        assert "n_subjects" in _clew_rows(project)

    def test_migration_is_announced(self, tmp_path, clew_store):
        # Arrange
        project = self._legacy_project(tmp_path)

        # Act
        result = list_claims(str(project))

        # Assert
        assert any("MIGRATING legacy" in n for n in result["notices"])

    def test_original_file_is_kept_as_a_backup(self, tmp_path, clew_store):
        # Arrange
        project = self._legacy_project(tmp_path)

        # Act
        list_claims(str(project))
        backup = project / "00_shared" / "claims.json.pre-clew"

        # Assert
        assert json.loads(backup.read_text()) == LEGACY

    def test_legacy_file_becomes_the_derived_export(self, tmp_path, clew_store):
        # Arrange
        project = self._legacy_project(tmp_path)

        # Act
        list_claims(str(project))
        export = json.loads((project / "00_shared" / "claims.json").read_text())

        # Assert
        assert export["_derived_from"] == DERIVED_MARKER

    def test_second_read_does_not_announce_again(self, tmp_path, clew_store):
        # Arrange
        project = self._legacy_project(tmp_path)
        list_claims(str(project))

        # Act
        result = list_claims(str(project))

        # Assert
        assert result["notices"] == []


# ---------------------------------------------------------------------------
# No store -> loud failure, no JSON fallback
# ---------------------------------------------------------------------------


class TestNoStoreFailsLoudly:
    """No ``clew_store`` fixture: SCITEX_STORE_DSN points at port 1."""

    def test_add_claim_fails_with_clew_unavailable(self, tmp_path):
        # Arrange
        project = _project(tmp_path)

        # Act
        result = add_claim(str(project), "acc", "value", {"value": 0.91})

        # Assert
        assert (result["success"], result.get("error_kind")) == (
            False,
            "clew_unavailable",
        )

    def test_add_claim_writes_no_local_json_as_fallback(self, tmp_path):
        # Arrange
        project = _project(tmp_path)

        # Act
        add_claim(str(project), "acc", "value", {"value": 0.91})

        # Assert
        assert not (project / "00_shared" / "claims.json").exists()

    def test_list_does_not_fall_back_to_reading_the_json(self, tmp_path):
        # Arrange: a perfectly readable legacy file is present
        project = _project(tmp_path)
        (project / "00_shared" / "claims.json").write_text(json.dumps(LEGACY))

        # Act
        result = list_claims(str(project))

        # Assert
        assert (result["success"], result.get("error_kind")) == (
            False,
            "clew_unavailable",
        )

    def test_render_fails_instead_of_rendering_the_json(self, tmp_path):
        # Arrange
        project = _project(tmp_path)
        (project / "00_shared" / "claims.json").write_text(json.dumps(LEGACY))

        # Act
        result = render_claims(str(project))

        # Assert
        assert (
            result["success"],
            (project / "00_shared" / "claims_rendered.tex").exists(),
        ) == (False, False)


@pytest.mark.parametrize("claim_type", ["citation"])
def test_writer_only_claim_type_maps_onto_a_clew_type(tmp_path, clew_store, claim_type):
    # Arrange: clew has no "citation" type; writer's type survives the trip.
    project = _project(tmp_path)

    # Act
    add_claim(str(project), "rep", claim_type, {"text": "70\\%"})

    # Assert
    assert (
        _clew_rows(project)["rep"].claim_type,
        get_claim(str(project), "rep")["claim"]["type"],
    ) == ("text", claim_type)


# EOF

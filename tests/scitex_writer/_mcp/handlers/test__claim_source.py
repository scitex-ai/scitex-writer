#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: src/scitex_writer/_mcp/handlers/_claim_source.py
#           and: scripts/python/check_claim_values.py

"""Value-vs-source: the number in the manuscript IS the number in its source.

A hash proves a source file is unchanged; it cannot prove the claim value was
copied from it correctly. These tests use real json/yaml/csv files and the
real clew store (``clew_store``) — no mocks.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scitex_writer._mcp.handlers._claim import add_claim, check_claim_values
from scitex_writer._mcp.handlers._claim_source import (
    SourceLocatorError,
    compare,
    implied_abs_tol,
    normalize_locator,
    read_source_value,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "python" / "check_claim_values.py"


# ---------------------------------------------------------------------------
# Locators (pure, real files)
# ---------------------------------------------------------------------------


class TestLocators:
    def test_json_pointer_reads_a_nested_list_element(self, tmp_path):
        # Arrange
        src = tmp_path / "m.json"
        src.write_text(json.dumps({"folds": [{"auc": 0.7}, {"auc": 0.8}]}))

        # Act
        value = read_source_value(src, normalize_locator("/folds/1/auc"))

        # Assert
        assert value == 0.8

    def test_json_pointer_unescapes_slash_in_keys(self, tmp_path):
        # Arrange: RFC 6901 "~1" is "/"
        src = tmp_path / "m.json"
        src.write_text(json.dumps({"a/b": 3}))

        # Act
        value = read_source_value(src, normalize_locator("/a~1b"))

        # Assert
        assert value == 3

    def test_yaml_source_is_read_with_the_same_pointer(self, tmp_path):
        # Arrange
        src = tmp_path / "m.yaml"
        src.write_text("stats:\n  t: 4.2317\n")

        # Act
        value = read_source_value(src, normalize_locator("/stats/t"))

        # Assert
        assert value == 4.2317

    def test_csv_cell_by_row_selector(self, tmp_path):
        # Arrange
        src = tmp_path / "t.csv"
        src.write_text("subject,auc\nS01,0.71\nS02,0.83\n")

        # Act
        value = read_source_value(src, {"row": {"subject": "S02"}, "column": "auc"})

        # Assert
        assert value == "0.83"

    def test_ambiguous_row_selector_is_an_error(self, tmp_path):
        # Arrange
        src = tmp_path / "t.csv"
        src.write_text("g,v\na,1\na,2\n")

        # Act
        def act():
            return read_source_value(src, {"row": {"g": "a"}, "column": "v"})

        # Assert
        with pytest.raises(SourceLocatorError, match="matched 2 rows"):
            act()

    def test_missing_key_is_an_error_not_none(self, tmp_path):
        # Arrange
        src = tmp_path / "m.json"
        src.write_text("{}")

        # Act
        def act():
            return read_source_value(src, normalize_locator("/absent"))

        # Assert
        with pytest.raises(SourceLocatorError, match="no key"):
            act()

    def test_pointer_against_a_csv_is_rejected(self, tmp_path):
        # Arrange
        src = tmp_path / "t.csv"
        src.write_text("a\n1\n")

        # Act
        def act():
            return read_source_value(src, normalize_locator("/a"))

        # Assert
        with pytest.raises(SourceLocatorError, match="pointer"):
            act()

    def test_locator_with_both_forms_is_rejected(self):
        # Arrange
        both = {"pointer": "/a", "row": 0, "column": "a"}

        # Act
        def act():
            return normalize_locator(both)

        # Assert
        with pytest.raises(SourceLocatorError, match="EITHER"):
            act()


class TestTolerance:
    @pytest.mark.parametrize(
        "written, expected",
        [("4.23", 0.005), ("34", 0.5), ("0.00032", 0.000005)],
    )
    def test_implied_tolerance_is_half_the_last_written_place(self, written, expected):
        # Arrange
        claimed = written

        # Act
        tol = implied_abs_tol(claimed)

        # Assert
        assert tol == pytest.approx(expected)

    def test_rounded_claim_matches_its_unrounded_source(self):
        # Arrange
        args = (4.23, 4.2317, {}, {})

        # Act
        ok, _ = compare(*args)

        # Assert
        assert ok is True

    def test_wrong_number_beyond_implied_tolerance_fails(self):
        # Arrange
        args = (4.23, 4.30, {}, {})

        # Act
        ok, _ = compare(*args)

        # Assert
        assert ok is False

    def test_declared_tolerance_overrides_the_implied_one(self):
        # Arrange: 0.9 vs 0.9134 passes at the implied +-0.05, so declare a
        # TIGHTER bound and expect failure.
        locator = {"abs_tol": 0.001}

        # Act
        ok, _ = compare(0.9, 0.9134, locator, {})

        # Assert
        assert ok is False

    def test_strings_compare_exactly(self):
        # Arrange
        args = ("ResNet-50", "ResNet-50 ", {}, {})

        # Act
        ok, _ = compare(*args)

        # Assert
        assert ok is True


# ---------------------------------------------------------------------------
# Through the store: registration-time refusal + pre-compile detection
# ---------------------------------------------------------------------------


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "paper"
    (project / "00_shared").mkdir(parents=True)
    (project / "results").mkdir()
    (project / "results" / "metrics.json").write_text(
        json.dumps({"test": {"auc": 0.9134, "n": 120}})
    )
    (project / "results" / "per_subject.csv").write_text(
        "subject,acc\nS01,0.71\nS02,0.83\n"
    )
    return project


def _register_auc(project, value=0.91):
    return add_claim(
        str(project),
        "auc",
        "value",
        {"value": value, "unit": ""},
        output_file="results/metrics.json",
        source_keys={"value": {"pointer": "/test/auc"}},
    )


class TestValueCheckThroughStore:
    def test_matching_claim_registers(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)

        # Act
        result = _register_auc(project)

        # Assert
        assert result["success"] is True, result

    def test_claim_contradicting_its_source_is_refused(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)

        # Act
        result = _register_auc(project, value=0.81)

        # Assert
        assert (result["success"], "disagrees with its source" in result["error"]) == (
            False,
            True,
        )

    def test_source_changed_after_registration_is_a_mismatch(
        self, tmp_path, clew_store
    ):
        # Arrange: registered while consistent, then the pipeline re-ran
        project = _project(tmp_path)
        _register_auc(project)
        (project / "results" / "metrics.json").write_text(
            json.dumps({"test": {"auc": 0.8412, "n": 120}})
        )

        # Act
        result = check_claim_values(str(project))

        # Assert
        assert [(m["claim_id"], m["field"]) for m in result["mismatches"]] == [
            ("auc", "value")
        ]

    def test_unchanged_source_passes(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)
        _register_auc(project)

        # Act
        result = check_claim_values(str(project))

        # Assert
        assert (result["ok"], len(result["checked"])) == (True, 1)

    def test_csv_cell_claim_is_checked(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)
        add_claim(
            str(project),
            "s02_acc",
            "value",
            {"value": 0.83},
            output_file="results/per_subject.csv",
            source_keys={"value": {"row": {"subject": "S02"}, "column": "acc"}},
        )
        (project / "results" / "per_subject.csv").write_text(
            "subject,acc\nS01,0.71\nS02,0.79\n"
        )

        # Act
        result = check_claim_values(str(project))

        # Assert
        assert [m["claim_id"] for m in result["mismatches"]] == ["s02_acc"]

    def test_claim_without_locator_is_reported_unchecked(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)
        add_claim(str(project), "n", "value", {"value": 120})

        # Act
        result = check_claim_values(str(project))

        # Assert
        assert result["unlocated"] == ["n"]


class TestPreCompileScript:
    def _run(self, project):
        return subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), str(project)],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_mismatch_blocks_the_compile(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)
        _register_auc(project)
        (project / "results" / "metrics.json").write_text(
            json.dumps({"test": {"auc": 0.5}})
        )

        # Act
        proc = self._run(project)

        # Assert
        assert (proc.returncode, "auc.value" in proc.stdout) == (1, True), (
            proc.stdout + proc.stderr
        )

    def test_consistent_claims_pass(self, tmp_path, clew_store):
        # Arrange
        project = _project(tmp_path)
        _register_auc(project)

        # Act
        proc = self._run(project)

        # Assert
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_unreachable_store_fails_instead_of_passing(self, tmp_path):
        # Arrange: claims exist (export present) but NO store is reachable
        project = _project(tmp_path)
        (project / "00_shared" / "claims.json").write_text(
            json.dumps({"claims": {"n": {"type": "value", "value": {"value": 1}}}})
        )

        # Act
        proc = self._run(project)

        # Assert
        assert (proc.returncode, "could NOT be checked" in proc.stdout) == (1, True)


# EOF

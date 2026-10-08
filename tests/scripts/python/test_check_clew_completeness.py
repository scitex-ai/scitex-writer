#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: check_clew_completeness.py (Defect A — the coverage gate)
#
# THE BUG THIS PINS. check_clew_verify delegates to `clew verify`, which reports
# a verdict over CLEW'S STORE — so it can pass having checked a claim set
# DISJOINT from what the manuscript renders. Measured on a real manuscript: 83
# rendered claims, 0 grounded, and the old gate said "0/1 verified". This gate
# reconciles the MANUSCRIPT set against clew's grounded set and reports coverage.
#
# The CLI reconciliation (`clew gate-completeness`) is validated by hand against
# the real manuscript (0/83, exit 1); these tests pin the PURE logic where the
# subtle bugs live — the manuscript set (raw claim_id, no sanitize) and the
# canonical-DB workdir resolution that made the denominator wrong until fixed.
# No mocks.

import json
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

_SCRIPT = ROOT_DIR / "scripts" / "python" / "check_clew_completeness.py"

from check_clew_completeness import (  # noqa: E402
    _resolve_clew_workdir,
    manuscript_claim_set,
)


class TestManuscriptClaimSet:
    def test_collects_vclaim_arguments(self, tmp_path):
        # Arrange
        c = tmp_path / "01_manuscript" / "contents"
        c.mkdir(parents=True)
        (c / "s.tex").write_text("Value: \\vclaim{group_effect}.\n")

        # Act
        ids = manuscript_claim_set(tmp_path)

        # Assert
        assert "group_effect" in ids

    def test_collects_claims_json_keys(self, tmp_path):
        # Arrange
        sh = tmp_path / "00_shared"
        sh.mkdir(parents=True)
        (sh / "claims.json").write_text(
            json.dumps({"claims": {"registered_one": {"type": "value"}}})
        )

        # Act
        ids = manuscript_claim_set(tmp_path)

        # Assert
        assert "registered_one" in ids

    def test_keeps_the_id_raw_without_sanitizing(self, tmp_path):
        # Arrange: the join key is the RAW claim_id (clew's identity). An
        # underscored id must survive verbatim — sanitizing it here would join
        # on the wrong string against clew's grounded set.
        c = tmp_path / "01_manuscript" / "contents"
        c.mkdir(parents=True)
        (c / "s.tex").write_text("\\vclaim{cohorta_inter_ncaps}\n")

        # Act
        ids = manuscript_claim_set(tmp_path)

        # Assert
        assert "cohorta_inter_ncaps" in ids


class TestResolveClewWorkdir:
    def test_walks_up_to_the_canonical_clew_dir(self, tmp_path):
        # Arrange: the vendored layout — manuscript at <repo>/.scitex/writer,
        # clew's canonical DB at <repo>/.scitex/clew. The workdir must resolve to
        # the repo root, or the gate reconciles against the wrong DB.
        repo = tmp_path
        (repo / ".scitex" / "clew").mkdir(parents=True)
        writer = repo / ".scitex" / "writer"
        writer.mkdir(parents=True)

        # Act
        resolved = _resolve_clew_workdir(writer)

        # Assert
        assert resolved == repo

    def test_falls_back_to_project_dir_when_no_clew_dir_exists(
        self, tmp_path, monkeypatch
    ):
        # Arrange: no .scitex/clew anywhere above — nothing to walk up to.
        # Hermetic: _resolve_clew_workdir walks ALL parents to /, so a
        # .scitex/clew store above pytest's tmp base (e.g. /home/runner on
        # CI runners) would otherwise leak in and break the fallback. Mask
        # clew-dir probes outside tmp_path so the test cannot escape it.
        proj = tmp_path / "plain"
        proj.mkdir()
        real_is_dir = Path.is_dir

        def _scoped_is_dir(self):
            if self.name == "clew" and self.parent.name == ".scitex":
                try:
                    self.relative_to(tmp_path)
                except ValueError:
                    return False
            return real_is_dir(self)

        monkeypatch.setattr(Path, "is_dir", _scoped_is_dir)

        # Act
        resolved = _resolve_clew_workdir(proj)

        # Assert
        assert resolved == proj

    def test_prefers_the_nearest_clew_dir_not_a_higher_one(self, tmp_path):
        # Arrange: if both a nested and an ancestor .scitex/clew exist, the
        # NEAREST wins (the project's own store, not a grandparent's).
        outer = tmp_path
        (outer / ".scitex" / "clew").mkdir(parents=True)
        inner = outer / "sub" / "project"
        (inner / ".scitex" / "clew").mkdir(parents=True)

        # Act
        resolved = _resolve_clew_workdir(inner)

        # Assert
        assert resolved == inner


def _run(project_dir, *extra):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(project_dir), *extra],
        capture_output=True,
        text=True,
    )


class TestEndToEnd:
    def test_off_level_disables_the_gate(self, tmp_path):
        # Arrange
        c = tmp_path / "01_manuscript" / "contents"
        c.mkdir(parents=True)
        (c / "s.tex").write_text("\\vclaim{anything}\n")

        # Act
        result = _run(tmp_path, "--level", "off")

        # Assert
        assert result.returncode == 0

    def test_no_manuscript_claims_passes(self, tmp_path):
        # Arrange: nothing rendered, nothing to reconcile — an honest pass, and
        # it must not even reach clew.
        c = tmp_path / "01_manuscript" / "contents"
        c.mkdir(parents=True)
        (c / "s.tex").write_text("Plain prose.\n")

        # Act
        result = _run(tmp_path, "--level", "error")

        # Assert
        assert result.returncode == 0

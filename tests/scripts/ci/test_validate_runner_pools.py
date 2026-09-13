"""Tests for scripts/ci/validate_runner_pools.py.

The guard stops a workflow from reading a RETIRED runner pool (scitex-ci /
spartan-cpu) into its runs-on — the class of defect that queues every PR forever
with no red signal. It validates the label against the supported/retired
convention (a pure function of the repo tree), not against the live runner census.

House style (scitex-app STX-TQ): one assertion per test (TQ007) and explicit
`# Arrange` / `# Act` / `# Assert` markers on their own lines (TQ002).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The guard lives under scripts/ci/ (not on the package path).
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import validate_runner_pools as v  # noqa: E402

FALLBACK_ORG_CPU = '${{ fromJSON(vars.CI_RUNS_ON || \'["self-hosted","Linux","X64","scitex-org-cpu"]\') }}'
FALLBACK_SCITEX_CI = '${{ fromJSON(vars.CI_RUNS_ON || \'["self-hosted","Linux","X64","scitex-ci"]\') }}'


def _write_workflow(repo: Path, name: str, runs_on: str) -> None:
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / name).write_text(
        "jobs:\n"
        f"  job:\n"
        f"    runs-on: {runs_on}\n"
        "    steps:\n"
        "      - run: echo hi\n",
        encoding="utf-8",
    )


@pytest.fixture()
def tmp_repo(tmp_path):
    _write_workflow(tmp_path, "stub.yml", FALLBACK_ORG_CPU)
    return tmp_path


# ---------------------------------------------------------------------------
# _pool_labels — the readable pool must be parsed from both spellings
# ---------------------------------------------------------------------------

def test_pool_labels_from_variable_fallback_seam():
    # Arrange: a variable-seam runs-on whose fallback names the supported pool.
    ro = FALLBACK_ORG_CPU
    # Act
    labels = v._pool_labels(ro)
    # Assert: the pool-selecting label is found (capability labels excluded).
    assert "scitex-org-cpu" in labels


def test_pool_labels_from_frozen_literal():
    # Arrange: a frozen literal runs-on (YAML flow list, double-quoted).
    ro = '["self-hosted", "Linux", "X64", "scitex-ci"]'
    # Act
    labels = v._pool_labels(ro)
    # Assert
    assert "scitex-ci" in labels


def test_pool_labels_excludes_generic_capability_labels():
    # Arrange: a supported-pool array with only capability + one pool label.
    ro = '["self-hosted", "Linux", "X64", "scitex-org-cpu"]'
    # Act
    labels = v._pool_labels(ro)
    # Assert: self-hosted/Linux/X64 are capability labels, so only the pool remains.
    assert labels == ["scitex-org-cpu"]


# ---------------------------------------------------------------------------
# check_repo — a retired pool in a workflow is a violation
# ---------------------------------------------------------------------------

def test_check_repo_flags_retired_pool_in_fallback(tmp_repo):
    # Arrange: one workflow whose fallback reads a retired pool.
    _write_workflow(tmp_repo, "x.yml", FALLBACK_SCITEX_CI)
    # Act
    viols = v.check_repo(tmp_repo)
    # Assert
    assert len(viols) == 1


def test_check_repo_flags_retired_pool_in_frozen_literal(tmp_repo):
    # Arrange: a workflow frozen to a retired pool.
    _write_workflow(tmp_repo, "y.yml", '["self-hosted", "Linux", "X64", "spartan-cpu"]')
    # Act
    viols = v.check_repo(tmp_repo)
    # Assert
    assert any(vv.pool == "spartan-cpu" for vv in viols)


def test_check_repo_passes_supported_pool(tmp_repo):
    # Arrange: the fixture repo already routes to the supported pool (stub.yml).
    _write_workflow(tmp_repo, "z.yml", FALLBACK_ORG_CPU)
    # Act
    viols = v.check_repo(tmp_repo)
    # Assert: no workflow reads a retired pool.
    assert viols == []


# ---------------------------------------------------------------------------
# the real repo must be clean after the fix (no workflow reads a retired pool)
# ---------------------------------------------------------------------------

def test_scitex_writer_repo_workflows_are_clean():
    # Arrange: the actual repository root.
    repo = REPO_ROOT
    # Act
    viols = v.check_repo(repo)
    # Assert: every scitex-writer workflow reads a supported pool.
    assert viols == []


def test_main_exit_code_is_one_when_dirty(tmp_repo, capsys):
    # Arrange: a workflow frozen to a retired pool.
    _write_workflow(tmp_repo, "dirty.yml", '["self-hosted", "Linux", "X64", "scitex-ci"]')
    # Act
    exit_code = v.main([str(tmp_repo)])
    # Assert: the guard fails loudly (exit 1) rather than passing a dead pool.
    assert exit_code == 1


def test_main_report_names_violations_when_dirty(tmp_repo, capsys):
    # Arrange: a workflow frozen to a retired pool.
    _write_workflow(tmp_repo, "dirty.yml", '["self-hosted", "Linux", "X64", "scitex-ci"]')
    # Act
    v.main([str(tmp_repo)])
    # Assert: the human report names the violation (triage is one read).
    assert "VIOLATIONS" in capsys.readouterr().out

"""Tests for scripts/ci/validate_runner_pools.py.

The guard stops a workflow from reading a RETIRED runner pool (scitex-ci /
spartan-cpu) into its runs-on — the class of defect that queues every PR forever
with no red signal. It validates the label against the supported/retired
convention (a pure function of the repo tree), not against the live runner census.
One assertion per test (STX-TQ007).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The guard lives under scripts/ci/ (not on the package path).
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import validate_runner_pools as v  # noqa: E402


# ---------------------------------------------------------------------------
# _pool_labels — the readable pool must be parsed from both spellings
# ---------------------------------------------------------------------------

def test_pool_labels_from_variable_fallback_seam():
    ro = '${{ fromJSON(vars.CI_RUNS_ON || \'["self-hosted","Linux","X64","scitex-org-cpu"]\') }}'
    assert "scitex-org-cpu" in v._pool_labels(ro)


def test_pool_labels_from_frozen_literal():
    ro = '["self-hosted", "Linux", "X64", "scitex-ci"]'
    assert "scitex-ci" in v._pool_labels(ro)


def test_pool_labels_excludes_generic_and_variable_refs():
    ro = '["self-hosted", "Linux", "X64", "scitex-org-cpu"]'
    labels = v._pool_labels(ro)
    assert labels == ["scitex-org-cpu"]  # self-hosted/Linux/X64 are capability labels


# ---------------------------------------------------------------------------
# check_repo — a retired pool in a workflow is a violation
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_repo(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    return tmp_path


def test_check_repo_flags_retired_pool_in_fallback(tmp_repo):
    (tmp_repo / ".github/workflows/x.yml").write_text(
        "jobs:\n"
        "  a:\n"
        '    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || \'["self-hosted","Linux","X64","scitex-ci"]\') }}\n'
        "    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )
    viols = v.check_repo(tmp_repo)
    assert len(viols) == 1


def test_check_repo_flags_retired_pool_in_frozen_literal(tmp_repo):
    (tmp_repo / ".github/workflows/y.yml").write_text(
        "jobs:\n  b:\n    runs-on: [\"self-hosted\", \"Linux\", \"X64\", \"spartan-cpu\"]\n"
        "    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )
    viols = v.check_repo(tmp_repo)
    assert any(vv.pool == "spartan-cpu" for vv in viols)


def test_check_repo_passes_supported_pool(tmp_repo):
    (tmp_repo / ".github/workflows/z.yml").write_text(
        "jobs:\n"
        "  c:\n"
        '    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || \'["self-hosted","Linux","X64","scitex-org-cpu"]\') }}\n'
        "    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )
    assert v.check_repo(tmp_repo) == []


# ---------------------------------------------------------------------------
# the real repo must be clean after the fix (no workflow reads a retired pool)
# ---------------------------------------------------------------------------

def test_scitex_writer_repo_workflows_are_clean():
    assert v.check_repo(REPO_ROOT) == []


def test_main_exit_code_clean_vs_dirty(tmp_repo, capsys):
    (tmp_repo / ".github/workflows/dirty.yml").write_text(
        "jobs:\n  d:\n    runs-on: [\"self-hosted\", \"Linux\", \"X64\", \"scitex-ci\"]\n"
        "    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )
    assert v.main([str(tmp_repo)]) == 1
    out = capsys.readouterr().out
    assert "VIOLATIONS" in out

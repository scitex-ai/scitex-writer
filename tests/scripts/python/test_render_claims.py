"""render_claims.py pre-compile step regenerates claims_rendered.tex from claims.json."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Claims are stored in scitex-clew (the one claim store): every test here
# needs the real store, on a throwaway schema.
pytestmark = pytest.mark.usefixtures("clew_store")


_SCRIPT = Path(__file__).resolve().parents[3] / "scripts/python/render_claims.py"


def _make_project(tmp_path, claims=None):
    shared = tmp_path / "00_shared"
    shared.mkdir(parents=True)
    if claims is not None:
        (shared / "claims.json").write_text(
            json.dumps({"version": "1.0", "claims": claims}), encoding="utf-8"
        )
    return tmp_path


def _run(project_dir):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(project_dir)],
        capture_output=True,
        text=True,
    )


def test_noop_when_no_claims_json(tmp_path):
    # Arrange
    project = _make_project(tmp_path, claims=None)
    # Act
    result = _run(project)
    # Assert
    assert (
        result.returncode == 0
        and not (project / "00_shared/claims_rendered.tex").exists()
    )


def test_renders_when_claims_json_present(tmp_path):
    # Arrange
    project = _make_project(
        tmp_path,
        claims={"foo": {"type": "value", "value": {"value": 42, "unit": "ms"}}},
    )
    # Act
    _run(project)
    # Assert
    assert "\\vclaim" in (project / "00_shared/claims_rendered.tex").read_text(
        encoding="utf-8"
    )


def test_regenerates_stale_file(tmp_path):
    # Arrange
    project = _make_project(
        tmp_path, claims={"foo": {"type": "value", "value": {"value": 1}}}
    )
    stale = project / "00_shared/claims_rendered.tex"
    stale.write_text("%% STALE CLEW PROTOTYPE BLOCK\n", encoding="utf-8")
    # Act
    _run(project)
    # Assert
    assert "STALE CLEW PROTOTYPE" not in stale.read_text(encoding="utf-8")


def _rendered_tex(tmp_path):
    """Generate claims_rendered.tex for a single value claim and return its text."""
    project = _make_project(
        tmp_path, claims={"foo": {"type": "value", "value": {"value": 1}}}
    )
    _run(project)
    return (project / "00_shared/claims_rendered.tex").read_text(encoding="utf-8")


def test_vclaim_defines_clew_color_helper(tmp_path):
    # Arrange
    project = tmp_path
    # Act
    tex = _rendered_tex(project)
    # Assert
    assert "\\v@claim@maybecolor" in tex


def test_vclaim_looks_up_clew_hex_by_id(tmp_path):
    # Arrange
    project = tmp_path
    # Act
    tex = _rendered_tex(project)
    # Assert
    assert "clew@hex@##1" in tex


def test_vclaim_reuses_clew_decorate_for_coloring(tmp_path):
    # Arrange
    project = tmp_path
    # Act
    tex = _rendered_tex(project)
    # Assert
    assert "\\clewDecorate{\\mbox{##2}}" in tex


def test_vclaim_guards_on_markers_toggle(tmp_path):
    # Arrange
    project = tmp_path
    # Act
    tex = _rendered_tex(project)
    # Assert
    assert "\\ifclewpresmarkers" in tex


def test_vclaim_plain_fallback_when_no_clew_hex(tmp_path):
    # Arrange: the \@ifundefined false-guard passes the plain value (##2)
    # through when no clew@hex@<id> is registered (claim not in the clew feed).
    project = tmp_path
    # Act
    tex = _rendered_tex(project)
    # Assert
    assert "\\@ifundefined{clew@hex@##1}{##2}" in tex

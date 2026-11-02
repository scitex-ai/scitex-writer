#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for pre-compile validation.

Tests validate_before_compile function for project structure validation.
"""

from pathlib import Path

import pytest

from scitex_writer._compile._validator import (
    _validate_provenance,
    _validate_styles_symlink,
    validate_before_compile,
)


class _StubRunner:
    """Real callable returning a canned check-result envelope.

    Injected via the ``runners=`` seam on _validate_provenance so the gate
    logic is exercised with real objects (no patching, no Mock) per the
    repo's no-mocks rule.
    """

    def __init__(self, result: dict):
        self.result = result

    def __call__(self, *args):
        return self.result


class TestValidateProvenance:
    """Test suite for the _validate_provenance compile-gate step."""

    def test_raises_when_check_at_error_with_violation(self):
        """A check returning a non-zero exit_code aborts the compile."""
        # Arrange
        err = {
            "success": True,
            "exit_code": 1,
            "stdout": "media: raw file foo.jpg",
            "summary": {"errors": 1},
        }
        runners = [("media-provenance", _StubRunner(err))]
        # Act
        # Assert
        with pytest.raises(RuntimeError):
            _validate_provenance(Path("/tmp/whatever"), runners=runners)

    def test_passes_when_no_violation(self):
        """A check at exit_code 0 does not raise."""
        # Arrange
        ok = {"success": True, "exit_code": 0, "summary": {}}
        runners = [("media-provenance", _StubRunner(ok))]
        # Act
        result = _validate_provenance(Path("/tmp/whatever"), runners=runners)
        # Assert
        assert result is None

    def test_skips_missing_check_script_without_raising(self):
        """A check whose script is absent (no exit_code) is skipped, not fatal."""
        # Arrange
        missing = {"success": False, "error": "check script not found"}
        runners = [("media-provenance", _StubRunner(missing))]
        # Act
        result = _validate_provenance(Path("/tmp/whatever"), runners=runners)
        # Assert
        assert result is None


def _make_project(tmp_path, doc_dir="01_manuscript", styles="symlink"):
    """Build a minimal project layout for the styles-symlink guard.

    ``styles``: "symlink" (canonical), "copy" (diverged local dir),
    "broken" (dangling symlink), or "absent".
    """
    shared = tmp_path / "00_shared" / "latex_styles"
    shared.mkdir(parents=True)
    contents = tmp_path / doc_dir / "contents"
    contents.mkdir(parents=True)
    target = contents / "latex_styles"
    if styles == "symlink":
        target.symlink_to("../../00_shared/latex_styles")
    elif styles == "copy":
        target.mkdir()
    elif styles == "broken":
        target.symlink_to("../../00_shared/no_such_dir")
    return tmp_path


class TestValidateStylesSymlink:
    """Test suite for the contents/latex_styles divergence guard."""

    def test_canonical_symlink_passes(self, tmp_path):
        """The template-canonical symlink into 00_shared does not raise."""
        # Arrange
        project = _make_project(tmp_path, styles="symlink")
        # Act
        result = _validate_styles_symlink(project, "manuscript")
        # Assert
        assert result is None

    def test_local_copy_raises_runtime_error(self, tmp_path):
        """A real local dir (the neurovista divergence) aborts the compile."""
        # Arrange
        project = _make_project(tmp_path, styles="copy")
        # Act
        # Assert
        with pytest.raises(RuntimeError):
            _validate_styles_symlink(project, "manuscript")

    def test_local_copy_error_names_the_fix(self, tmp_path):
        """The divergence error carries the actionable ln -s hint."""
        # Arrange
        project = _make_project(tmp_path, styles="copy")
        # Act
        # Assert
        with pytest.raises(RuntimeError, match=r"ln -s \.\./\.\./00_shared/latex_styles"):
            _validate_styles_symlink(project, "manuscript")

    def test_broken_symlink_raises_runtime_error(self, tmp_path):
        """A dangling latex_styles symlink aborts the compile."""
        # Arrange
        project = _make_project(tmp_path, styles="broken")
        # Act
        # Assert
        with pytest.raises(RuntimeError):
            _validate_styles_symlink(project, "manuscript")

    def test_supplementary_copy_raises_runtime_error(self, tmp_path):
        """The guard also covers 02_supplementary."""
        # Arrange
        project = _make_project(tmp_path, doc_dir="02_supplementary", styles="copy")
        # Act
        # Assert
        with pytest.raises(RuntimeError):
            _validate_styles_symlink(project, "supplementary")

    def test_revision_doc_type_is_exempt(self, tmp_path):
        """Revision ships a real local styles dir in the template — no raise."""
        # Arrange
        project = _make_project(tmp_path, doc_dir="03_revision", styles="copy")
        # Act
        result = _validate_styles_symlink(project, "revision")
        # Assert
        assert result is None

    def test_absent_styles_path_is_skipped(self, tmp_path):
        """Missing latex_styles is the tree check's concern, not this guard's."""
        # Arrange
        project = _make_project(tmp_path, styles="absent")
        # Act
        result = _validate_styles_symlink(project, "manuscript")
        # Assert
        assert result is None

    def test_project_without_00_shared_is_skipped(self, tmp_path):
        """A layout with no 00_shared has nothing to diverge from — no raise."""
        # Arrange
        (tmp_path / "01_manuscript" / "contents" / "latex_styles").mkdir(parents=True)
        # Act
        result = _validate_styles_symlink(tmp_path, "manuscript")
        # Assert
        assert result is None


class TestValidateBeforeCompile:
    """Test suite for validate_before_compile function."""

    def test_import_callable_validate_before_compile(self):
        """Test that validate_before_compile can be imported."""
        # Arrange
        # Act
        # Assert
        assert callable(validate_before_compile)

    def test_validate_nonexistent_directory(self):
        """Test validation fails for non-existent directory."""
        # Arrange
        # Act
        project_dir = Path("/tmp/nonexistent-project-12345")
        # Assert
        with pytest.raises(Exception):
            validate_before_compile(project_dir)

    def test_validate_accepts_path_object_without_type_error(self):
        """validate_before_compile accepts a Path argument (no TypeError).

        A missing/invalid project may raise validation errors — that's
        fine; the contract under test is that passing a Path is itself
        accepted (no TypeError about the argument type).
        """
        # Arrange
        project_dir = Path("/tmp/test")
        raised_type_error = False
        # Act
        try:
            validate_before_compile(project_dir)
        except TypeError:
            raised_type_error = True
        except Exception:
            # Validation-level errors are acceptable for this contract.
            pass
        # Assert
        assert raised_type_error is False


# EOF

if __name__ == "__main__":
    import os

    import pytest

    pytest.main([os.path.abspath(__file__)])

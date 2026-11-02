#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for supplementary materials compilation.

compile_supplementary is a thin wrapper that forwards its options to the
run_compile worker with doc_type 'supplementary'. The tests inject a real
recording runner via the runner= seam and assert the forwarded args — no
patching of run_compile, no real LaTeX toolchain.
"""

import inspect
from pathlib import Path

import pytest

from scitex_writer._compile.supplementary import compile_supplementary
from scitex_writer._dataclasses import CompilationResult


class _RecordingRunner:
    """Real run_compile stand-in: records (args, kwargs), returns a result."""

    def __init__(self, result=None):
        self.calls = []
        self.result = result or CompilationResult(
            success=True, exit_code=0, stdout="", stderr="", duration=1.0
        )

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


_PROJECT_DIR = Path("/tmp/test-project")


class TestCompileSupplementarySignature:
    """Signature / import contract."""

    def test_compile_supplementary_is_importable_callable(self):
        # Arrange
        from scitex_writer._compile import compile_supplementary as cs

        # Act
        # Assert
        assert callable(cs)

    def test_signature_exposes_all_documented_parameters(self):
        # Arrange
        expected = {
            "project_dir",
            "timeout",
            "no_figs",
            "ppt2tif",
            "crop_tif",
            "quiet",
            "log_callback",
            "progress_callback",
        }
        # Act
        params = set(inspect.signature(compile_supplementary).parameters)
        # Assert
        assert expected <= params

    def test_default_timeout_is_300(self):
        # Arrange
        # Act
        sig = inspect.signature(compile_supplementary)
        # Assert
        assert sig.parameters["timeout"].default == 300

    def test_default_boolean_flags_are_false(self):
        # Arrange
        sig = inspect.signature(compile_supplementary)
        flags = ("no_figs", "ppt2tif", "crop_tif", "quiet")
        # Act
        defaults = [sig.parameters[f].default for f in flags]
        # Assert
        assert defaults == [False] * len(flags)

    def test_default_callbacks_are_none(self):
        # Arrange
        sig = inspect.signature(compile_supplementary)
        # Act
        defaults = (
            sig.parameters["log_callback"].default,
            sig.parameters["progress_callback"].default,
        )
        # Assert
        assert defaults == (None, None)


class TestCompileSupplementaryDelegation:
    """Forwarding contract to the run_compile worker."""

    def test_forwards_supplementary_doc_type_as_first_arg(self):
        # Arrange
        runner = _RecordingRunner()
        # Act
        compile_supplementary(_PROJECT_DIR, runner=runner)
        # Assert
        assert runner.calls[0][0][0] == "supplementary"

    def test_forwards_project_dir_as_second_arg(self):
        # Arrange
        runner = _RecordingRunner()
        # Act
        compile_supplementary(_PROJECT_DIR, runner=runner)
        # Assert
        assert runner.calls[0][0][1] == _PROJECT_DIR

    def test_forwards_no_figs_option(self):
        # Arrange
        runner = _RecordingRunner()
        # Act
        compile_supplementary(_PROJECT_DIR, no_figs=True, runner=runner)
        # Assert
        assert runner.calls[0][1]["no_figs"] is True

    def test_forwards_ppt2tif_option(self):
        # Arrange
        runner = _RecordingRunner()
        # Act
        compile_supplementary(_PROJECT_DIR, ppt2tif=True, runner=runner)
        # Assert
        assert runner.calls[0][1]["ppt2tif"] is True

    def test_forwards_crop_tif_option(self):
        # Arrange
        runner = _RecordingRunner()
        # Act
        compile_supplementary(_PROJECT_DIR, crop_tif=True, runner=runner)
        # Assert
        assert runner.calls[0][1]["crop_tif"] is True

    def test_forwards_quiet_option(self):
        # Arrange
        runner = _RecordingRunner()
        # Act
        compile_supplementary(_PROJECT_DIR, quiet=True, runner=runner)
        # Assert
        assert runner.calls[0][1]["quiet"] is True

    def test_forwards_log_callback(self):
        # Arrange
        runner = _RecordingRunner()

        def _log(_line):
            return None

        # Act
        compile_supplementary(_PROJECT_DIR, log_callback=_log, runner=runner)
        # Assert
        assert runner.calls[0][1]["log_callback"] is _log

    def test_forwards_progress_callback(self):
        # Arrange
        runner = _RecordingRunner()

        def _progress(_pct, _step):
            return None

        # Act
        compile_supplementary(_PROJECT_DIR, progress_callback=_progress, runner=runner)
        # Assert
        assert runner.calls[0][1]["progress_callback"] is _progress

    def test_returns_runner_result_unchanged(self):
        # Arrange
        expected = CompilationResult(
            success=True, exit_code=0, stdout="Test output", stderr="", duration=2.5
        )
        runner = _RecordingRunner(result=expected)
        # Act
        result = compile_supplementary(_PROJECT_DIR, runner=runner)
        # Assert
        assert result is expected


if __name__ == "__main__":
    import os

    pytest.main([os.path.abspath(__file__)])

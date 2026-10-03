"""Smoke test: `scitex_writer.compile` imports cleanly."""

import importlib
import sys

import pytest


class _CompileBoundaryReached(BaseException):
    """Stop before the real compile-script body without claiming a result."""


def _capture_compile_call(function, project_dir, *args, **kwargs):
    from scitex_writer._mcp.utils import run_compile_script

    calls = []
    previous = sys.gettrace()

    def observe(frame, event, arg):
        if event == "call" and frame.f_code is run_compile_script.__code__:
            calls.append(dict(frame.f_locals))
            raise _CompileBoundaryReached
        return observe

    sys.settrace(observe)
    try:
        function(str(project_dir), *args, **kwargs)
    except _CompileBoundaryReached:
        pass
    finally:
        sys.settrace(previous)
    return calls


@pytest.fixture
def workspace(tmp_path):
    """Disposable interface input; no compiler, claims or scientific data."""
    for name in ("00_shared", "01_manuscript", "02_supplementary", "03_revision"):
        (tmp_path / name).mkdir()
    (tmp_path / "00_shared/synthetic-interface-input.txt").write_text("Synthetic input.\n")
    return tmp_path


def test_module_exposes_manuscript():
    # Arrange
    # Act
    module = importlib.import_module("scitex_writer.compile")
    # Assert
    assert hasattr(module, "manuscript")


@pytest.mark.parametrize("name", ["supplementary", "revision"])
@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("dark_mode", [False, True])
@pytest.mark.parametrize("return_as", [None, "result"])
def test_decorated_document_compile_forwards_requested_dark_mode(
    workspace, name, draft, dark_mode, return_as
):
    # Arrange
    function = getattr(importlib.import_module("scitex_writer.compile"), name)
    # Act
    calls = _capture_compile_call(
        function, workspace, draft=draft, dark_mode=dark_mode,
        quiet=True, return_as=return_as,
    )
    # Assert
    assert calls[0]["dark_mode"] is dark_mode


@pytest.mark.parametrize("name", ["supplementary", "revision"])
@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("dark_mode", [False, True])
@pytest.mark.parametrize("return_as", [None, "result"])
def test_decorated_document_compile_preserves_requested_draft_mode(
    workspace, name, draft, dark_mode, return_as
):
    # Arrange
    function = getattr(importlib.import_module("scitex_writer.compile"), name)
    # Act
    calls = _capture_compile_call(
        function, workspace, draft=draft, dark_mode=dark_mode,
        quiet=True, return_as=return_as,
    )
    # Assert
    assert calls[0]["draft"] is draft


@pytest.mark.parametrize("name", ["supplementary", "revision"])
@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("dark_mode", [False, True])
@pytest.mark.parametrize("return_as", [None, "result"])
def test_decorated_document_compile_preserves_requested_document_type(
    workspace, name, draft, dark_mode, return_as
):
    # Arrange
    function = getattr(importlib.import_module("scitex_writer.compile"), name)
    # Act
    calls = _capture_compile_call(
        function, workspace, draft=draft, dark_mode=dark_mode,
        quiet=True, return_as=return_as,
    )
    # Assert
    assert calls[0]["doc_type"] == name


@pytest.mark.parametrize("name", ["supplementary", "revision"])
@pytest.mark.parametrize("draft", [False, True])
def test_omitted_dark_mode_preserves_existing_light_default(workspace, name, draft):
    # Arrange
    function = getattr(importlib.import_module("scitex_writer.compile"), name)
    # Act
    calls = _capture_compile_call(function, workspace, draft=draft, quiet=True)
    # Assert
    assert calls[0]["dark_mode"] is False


@pytest.mark.parametrize("name,leading", [
    ("supplementary", (11, True, True, True, True)),
    ("revision", (True, 13, False, False)),
])
@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("engine", [None, "synthetic-engine"])
def test_legacy_positional_arguments_preserve_quiet_slot(
    workspace, name, leading, quiet, engine
):
    # Arrange
    function = getattr(importlib.import_module("scitex_writer.compile"), name)
    # Act
    calls = _capture_compile_call(function, workspace, *leading, quiet, engine)
    # Assert
    assert calls[0]["quiet"] is quiet


@pytest.mark.parametrize("name,leading", [
    ("supplementary", (11, True, True, True, True)),
    ("revision", (True, 13, False, False)),
])
@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("engine", [None, "synthetic-engine"])
def test_legacy_positional_arguments_preserve_engine_slot(
    workspace, name, leading, quiet, engine
):
    # Arrange
    function = getattr(importlib.import_module("scitex_writer.compile"), name)
    # Act
    calls = _capture_compile_call(function, workspace, *leading, quiet, engine)
    # Assert
    assert calls[0]["engine"] == engine


@pytest.mark.parametrize("name", ["supplementary", "revision"])
def test_default_document_compile_preserves_quiet_default(workspace, name):
    # Arrange
    function = getattr(importlib.import_module("scitex_writer.compile"), name)
    # Act
    calls = _capture_compile_call(function, workspace)
    # Assert
    assert calls[0]["quiet"] is False


@pytest.mark.parametrize("name", ["supplementary", "revision"])
def test_default_document_compile_preserves_timeout_default(workspace, name):
    # Arrange
    function = getattr(importlib.import_module("scitex_writer.compile"), name)
    # Act
    calls = _capture_compile_call(function, workspace)
    # Assert
    assert calls[0]["timeout"] == 300


@pytest.mark.parametrize("name", ["supplementary", "revision"])
def test_default_document_compile_preserves_engine_default(workspace, name):
    # Arrange
    function = getattr(importlib.import_module("scitex_writer.compile"), name)
    # Act
    calls = _capture_compile_call(function, workspace)
    # Assert
    assert calls[0]["engine"] is None

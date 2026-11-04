"""Pins the paper-symlink default severity in scitex_writer.__init__.

Locks the off -> warn flip so a future edit cannot silently revert the
package-level resolver default.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest

from scitex_writer import _resolve_paper_symlink_level


@pytest.fixture
def clean_paper_env():
    """Isolate env + HOME (real os.environ, restored on teardown) so neither
    SCITEX_WRITER_PAPER_SYMLINK nor a user config.yaml leaks into resolution."""
    saved = {k: os.environ.get(k) for k in ("SCITEX_WRITER_PAPER_SYMLINK", "HOME")}
    os.environ.pop("SCITEX_WRITER_PAPER_SYMLINK", None)
    with tempfile.TemporaryDirectory() as home:
        os.environ["HOME"] = home
        yield home
    for key, val in saved.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


def test_resolve_paper_symlink_level_defaults_to_warn(tmp_path, clean_paper_env):
    """With no env and no user config, the resolved default level is warn."""
    # Arrange
    project_dir = str(tmp_path)
    # Act
    level = _resolve_paper_symlink_level(project_dir)
    # Assert
    assert level == "warn"


_PUBLIC_CATALOG_SCRIPT = """
import importlib
import inspect
import json
import scitex_writer as writer

warm_first = WARM_FIRST
if warm_first:
    from scitex_writer.writer import Writer
before = {name for name in dir(writer) if not name.startswith('_')}
first = {name for name, value in inspect.getmembers(writer)
         if not name.startswith('_')}
from scitex_writer.writer import Writer
second = {name for name, value in inspect.getmembers(writer)
          if not name.startswith('_')}
print(json.dumps({
    'before': sorted(before), 'first': sorted(first), 'second': sorted(second),
    'declared': sorted(set(writer.__all__) | set(writer._LAZY_SUBMODULES)),
    'same_class': writer.Writer is Writer,
    'submodule_accessible': importlib.import_module('scitex_writer.writer').Writer is Writer,
}))
"""


@pytest.mark.parametrize("warm_first", [False, True])
def test_public_catalog_is_stable_across_lazy_writer_loading(warm_first):
    """A lazy class import must not advertise its incidental backing module."""
    # Arrange
    script = _PUBLIC_CATALOG_SCRIPT.replace("WARM_FIRST", repr(warm_first))
    # Act
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True,
        check=True, timeout=30,
    )
    catalog = json.loads(result.stdout)
    declared = [name for name in catalog["declared"] if not name.startswith("_")]
    # Assert
    assert catalog == {
        "before": declared, "first": declared, "second": declared,
        "declared": catalog["declared"], "same_class": True,
        "submodule_accessible": True,
    }

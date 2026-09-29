"""Subprocess isolation: HOME/SCITEX_DIR point at tmp, never the real home.

Real ``os.environ`` save/restore, not ``monkeypatch`` — the child CLI
process inherits the REAL environment, so only real mutation isolates it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture()
def isolated_home(tmp_path: Path) -> Iterator[Path]:
    """Redirect HOME-derived state (scitex log files, caches) at tmp."""
    names = ("HOME", "SCITEX_DIR")
    previous = {name: os.environ.get(name) for name in names}
    scratch = tmp_path / "home"
    scratch.mkdir()
    os.environ["HOME"] = str(scratch)
    os.environ["SCITEX_DIR"] = str(scratch / ".scitex")
    try:
        yield scratch
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

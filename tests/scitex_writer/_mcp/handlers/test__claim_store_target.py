#!/usr/bin/env python3
"""Which store a compile writes claims to — never a deployment it was not told.

scitex-writer#516: with ``SCITEX_STORE_DSN`` unset, ``compile`` (via
``render_claims`` -> ``_claim_store.sync``) migrated a project's claims into
the fleet's central store, ``scitex-primary:55432``, without naming it. The
target now resolves exactly as clew resolves it (``scitex-dev >= 0.67.0``):
the explicit DSN, else the per-user local store; and the target is named in
every write notice.

Real ``os.environ`` fixtures restore on teardown; resolution is inert, so no
database is opened here.
"""

from __future__ import annotations

import os
from typing import Iterator

import pytest

from scitex_writer._mcp.handlers._claim_store import claims_store_description

_ISOLATED = ("SCITEX_STORE_DSN", "HOME", "SCITEX_DIR")


@pytest.fixture
def fresh_machine(tmp_path) -> Iterator[None]:
    saved = {key: os.environ.get(key) for key in _ISOLATED}
    os.environ.pop("SCITEX_STORE_DSN", None)
    os.environ.pop("SCITEX_DIR", None)
    os.environ["HOME"] = str(tmp_path)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_an_unset_dsn_never_targets_the_fleet_host(fresh_machine):
    # Arrange
    pytest.importorskip("scitex_dev.store._local")
    # Act
    described = claims_store_description()
    # Assert
    assert "scitex-primary" not in described


def test_an_explicit_dsn_is_the_named_target(fresh_machine):
    # Arrange
    os.environ["SCITEX_STORE_DSN"] = "postgresql://someone@db.example:55432/papers"
    # Act
    described = claims_store_description()
    # Assert
    assert "db.example" in described


# EOF

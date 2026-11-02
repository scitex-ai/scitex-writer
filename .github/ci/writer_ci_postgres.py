"""Leaf CI PostgreSQL resource shared by the SIF driver and pytest hook."""

from __future__ import annotations

import contextlib
import os
import signal
import tempfile
from urllib.parse import parse_qs, urlsplit

from scitex_dev.store.testing import ephemeral_cluster_dsn

_TEST_KEYS = {
    "SCITEX_WRITER_TEST_PG_DSN",
    "SCITEX_WRITER_TEST_PG_REQUIRED",
    "SCITEX_STORE_DSN",
    "SCITEX_CARDS_DB",
}


def _interrupted(signum, _frame):
    raise SystemExit(128 + signum)


@contextlib.contextmanager
def private_postgres_environment(interrupt=None):
    """Require a new private cluster; restore only owned environment on exit."""
    previous = {
        name: value
        for name, value in os.environ.items()
        if name.startswith("PG") or name in _TEST_KEYS
    }
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for sig in handlers:
            signal.signal(sig, interrupt or _interrupted)
        for name in tuple(os.environ):
            if name.startswith("PG"):
                os.environ.pop(name, None)
        os.environ["PGPORT"] = "5432"
        with contextlib.ExitStack() as owned:
            authfile = owned.enter_context(
                tempfile.NamedTemporaryFile(prefix="writer-ci-pgpass-")
            )
            os.environ["PGPASSFILE"] = authfile.name
            # No configured DSN is consulted, and missing tools never become skips.
            dsn = owned.enter_context(ephemeral_cluster_dsn())
            selected = urlsplit(dsn)
            socket = parse_qs(selected.query)["host"][0]
            if selected.hostname is not None or not socket.startswith("/"):
                raise RuntimeError(
                    "Writer CI PostgreSQL must use its private Unix socket"
                )
            os.environ.update(
                SCITEX_WRITER_TEST_PG_DSN=dsn,
                SCITEX_WRITER_TEST_PG_REQUIRED="1",
                SCITEX_STORE_DSN=dsn,
                SCITEX_CARDS_DB=dsn,
                PGHOST=socket,
                PGPORT="5432",
                PGDATABASE="postgres",
                PGUSER="postgres",
                PGPASSFILE=authfile.name,
            )
            try:
                yield dict(os.environ)
            finally:
                # Do not interrupt database teardown halfway through. The owning
                # CI shell retains its bounded child-group cancellation fence.
                for sig in handlers:
                    signal.signal(sig, signal.SIG_IGN)
    finally:
        for name in tuple(os.environ):
            if name.startswith("PG") or name in _TEST_KEYS:
                os.environ.pop(name, None)
        os.environ.update(previous)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def _pytest_interrupted(signum, _frame):
    import pytest

    pytest.exit("Writer CI cancelled", returncode=128 + signum)


def pytest_load_initial_conftests(early_config, parser, args):
    """Start once in the controller before root conftest/xdist read the DSN."""
    if os.environ.get("PYTEST_XDIST_WORKER"):
        dsn = os.environ.get("SCITEX_WRITER_TEST_PG_DSN", "")
        socket = parse_qs(urlsplit(dsn).query).get("host", [""])[0]
        if os.environ.get(
            "SCITEX_WRITER_TEST_PG_REQUIRED"
        ) != "1" or not socket.startswith("/"):
            raise RuntimeError(
                "Writer CI worker did not inherit its private required PostgreSQL"
            )
        return
    owned = contextlib.ExitStack()
    early_config.add_cleanup(owned.close)
    owned.enter_context(private_postgres_environment(_pytest_interrupted))

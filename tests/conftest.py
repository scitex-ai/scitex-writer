"""Pytest fixtures and rootdir marker for this package.

An empty conftest.py at tests/ is the canonical SciTeX
convention (audit-project PS208) — it pins the pytest
rootdir and gives downstream fixtures a home.

Module-import-time coverage wiring (parallel + subprocess support).
`os.environ.setdefault` would be a no-op here because pytest-cov has
already set COVERAGE_FILE to a tmp dir by the time conftest is loaded.
See `_skills/general/05_development_06_subprocess-coverage.md`.

Also the PostgreSQL store isolation used by every store-backed test — see
`_no_accidental_fleet_store_writes` and `pg_schema` below. This is the
ROOTDIR conftest, so both reach `tests/integration/`, `tests/develop/` and
`tests/examples/` as well as `tests/scitex_writer/`; putting them one level
down would leave those siblings unprotected.
"""
from __future__ import annotations

import getpass
import os
import sysconfig
from pathlib import Path
from typing import Iterator

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Pin coverage's data file at the repo root and point process_startup
# at our pyproject so child interpreters configure themselves correctly.
os.environ["COVERAGE_PROCESS_START"] = str(_PROJECT_ROOT / "pyproject.toml")
os.environ["COVERAGE_FILE"] = str(_PROJECT_ROOT / ".coverage")

# scitex-logging defaults to WARN, which would silence log.info/DEBUG
# diagnostics the suite (and smoke children) should see. INFO keeps the
# CLI-output contract tests meaningful without flooding.
os.environ.setdefault("SCITEX_LOGGING_LEVEL", "INFO")
try:
    import scitex_logging as _slogging

    _slogging.set_level("INFO")
except Exception:  # pragma: no cover - logging must never break collection
    pass


def _ensure_subprocess_coverage_shim() -> None:
    """Drop an idempotent `.pth` file in site-packages that auto-starts
    coverage in every child Python interpreter via
    `coverage.process_startup()`.
    """
    purelib = Path(sysconfig.get_paths()["purelib"])
    pth = purelib / "_scitex_writer_subprocess_coverage.pth"
    shim = (
        "import os, coverage\n"
        "if os.environ.get('COVERAGE_PROCESS_START'):\n"
        "    coverage.process_startup()\n"
    )
    try:
        if not pth.exists() or pth.read_text() != shim:
            pth.write_text(shim)
    except OSError:
        # site-packages may be read-only (e.g. system Python); silently
        # skip — local dev venvs are writable and that's where this matters.
        pass


_ensure_subprocess_coverage_shim()


# ---------------------------------------------------------------------------
# PostgreSQL store isolation
# ---------------------------------------------------------------------------
# Writer's state lives in the fleet store (`scitex_dev.store`), which resolves
# `SCITEX_STORE_DSN` — a FLEET-WIDE variable every agent container carries. A
# test that persists an annotation therefore writes into the LIVE store unless
# something stops it, and a best-effort caller swallows the failure, so such a
# test looks identical to one that does not — right up until someone counts
# the rows.

#: A DSN that cannot reach anything, on purpose. Port 1 refuses instantly, and
#: the database name is written to be legible in the error a stray write
#: produces — the message states the rule it just enforced.
_UNREACHABLE_DSN = (
    "postgresql://writer_tests@127.0.0.1:1/tests_must_not_write_to_the_fleet_store"
)

#: The fleet CARDS board, isolated for the same reason and by the same means.
#:
#: MEASURED 2026-08-29. `_annotations._emit` posts an annotation summary to the
#: manuscript's owning card, and `scitex_cards` resolves `$SCITEX_CARDS_DB` —
#: the live fleet board — whenever the explicit store it is handed does not
#: exist. Several tests deliberately pass a NON-EXISTENT tmp store to exercise
#: the notify-failed path, so every one of them commented on the real board
#: instead. The card `writer-annotations-proj` on the fleet board carries those
#: fixture comments, the oldest dated 2026-08-18; that is what an unisolated
#: rail looks like after a few CI runs. Repointing the variable is what stops
#: it, and it belongs here rather than in one test file because the leak came
#: from the DEFAULT resolution, not from any single call site.
_CARDS_DB_KEY = "SCITEX_CARDS_DB"

#: The database store-backed tests are pointed at. Loopback by default; every
#: fleet PostgreSQL refuses non-local connections at pg_hba.
PG_BASE_DSN = os.environ.get(
    "SCITEX_WRITER_TEST_PG_DSN", "postgresql://127.0.0.1:55432/scitex"
)

#: Was the target DECLARED, or did we fall back to the default? The
#: distinction decides skip-vs-fail. "This machine has no cluster" is a fact
#: about a machine and may be skipped; "the target somebody configured does
#: not work" is a misconfiguration, and a misconfiguration that skips is
#: indistinguishable from a pass.
PG_DSN_WAS_DECLARED = "SCITEX_WRITER_TEST_PG_DSN" in os.environ

#: Set to "1" to make an unusable target a hard FAILURE rather than a skip.
#: Intended for a release gate: a PR may proceed with store coverage skipped,
#: a tag must not publish having silently run none of it.
PG_REQUIRED = os.environ.get("SCITEX_WRITER_TEST_PG_REQUIRED") == "1"

#: The fleet's replication cluster, which tests must NEVER create schemas in.
#: Every node reports this identifier, so one comparison recognises the
#: production cluster no matter which host the DSN resolves to and no matter
#: which node is primary today — a guard naming a HOST would protect the wrong
#: machine the moment the primary moves.
FLEET_SYSTEM_ID = os.environ.get(
    "SCITEX_WRITER_TEST_PG_FORBIDDEN_SYSTEM_ID", "7672112238472680366"
)

#: Resolved AT IMPORT, while HOME is still the real one: several tests sandbox
#: HOME, and libpq would then look for `~/.pgpass` in an empty directory.
_PGPASS_AT_IMPORT = os.environ.get("PGPASSFILE") or os.path.expanduser("~/.pgpass")


def _default_test_pg_user() -> str:
    """The login role tests authenticate as when nothing declares one.

    Derived, never hardcoded: fleet roles are `<os-user>__<consumer>` and the
    owner varies by machine. It must be a LOGIN role — libpq's own fallback is
    the bare OS user, which in this role tree is a NOLOGIN umbrella.
    """
    return f"{getpass.getuser()}__cli"


PG_TEST_USER = os.environ.get("PGUSER") or _default_test_pg_user()

# SET AT IMPORT, not only inside the fixture: a conftest is imported before
# anything under its directory is collected, so this covers collection and
# module/session-scoped fixtures too — the windows a function-scoped fixture
# cannot reach.
os.environ["SCITEX_STORE_DSN"] = _UNREACHABLE_DSN
os.environ[_CARDS_DB_KEY] = _UNREACHABLE_DSN


@pytest.fixture(autouse=True)
def _no_accidental_fleet_store_writes() -> Iterator[None]:
    """Point every test at stores that cannot exist, unless it asks otherwise.

    An unreachable DSN rather than a throwaway schema: a schema per test would
    CONNECT, which would make every test in this suite depend on PostgreSQL
    being up. This costs nothing and cannot be skipped — there is no server on
    port 1, so a stray write raises immediately.

    Both the state store and the cards board are repointed. A test that hands
    `scitex_cards` an explicit tmp store still uses it; one that hands it a
    path that does not exist now fails to reach ANY board, which is what those
    tests were written to assert, instead of silently reaching the live one.

    Tests that need a REAL store take `pg_schema`, which DEPENDS on this
    fixture and overwrites the variable afterwards, so the ordering is
    guaranteed by the dependency rather than by pytest's autouse rules.
    """
    keys = ("SCITEX_STORE_DSN", _CARDS_DB_KEY)
    saved = {key: os.environ.get(key) for key in keys}
    for key in keys:
        os.environ[key] = _UNREACHABLE_DSN
    try:
        yield
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


@pytest.fixture()
def pg_schema(_no_accidental_fleet_store_writes: None) -> Iterator[str]:
    """A throwaway PostgreSQL schema, wired in via `SCITEX_STORE_DSN`.

    Yields the schema name. Anything a module-under-test writes through
    `scitex_dev.store` lands here and is dropped afterwards, so live fleet
    state is never touched.

    NOT autouse: it CONNECTS, and a test that does not need PostgreSQL must
    not fail because PostgreSQL is down.

    A SCHEMA rather than a database, deliberately: creating a database needs
    CREATEDB and the fleet is not uniform there, so a create-a-database
    fixture would pass on some runners and fail on others — a flake that looks
    like the code. The name carries a uuid because the python matrix can put
    concurrent jobs on one runner.

    Real `os.environ` save/restore, not `monkeypatch` — the point is that the
    REAL resolver reads the REAL variable.
    """
    import uuid

    import psycopg

    pgpass_key, pguser_key = "PGPASSFILE", "PGUSER"
    saved_pgpass = os.environ.get(pgpass_key)
    saved_pguser = os.environ.get(pguser_key)
    os.environ[pgpass_key] = _PGPASS_AT_IMPORT
    os.environ[pguser_key] = PG_TEST_USER

    schema = "writer_test_" + uuid.uuid4().hex[:12]

    def _restore_identity() -> None:
        for key_, saved_ in ((pgpass_key, saved_pgpass), (pguser_key, saved_pguser)):
            if saved_ is None:
                os.environ.pop(key_, None)
            else:
                os.environ[key_] = saved_

    def _unusable(reason: str, *, hard: bool) -> None:
        """Report an unusable target loudly — never silently.

        The reason names the DSN and the role, so a skip on a host that is
        SUPPOSED to have a writable database reads as the misconfiguration it
        is instead of disappearing into a skip count. Visibility comes from
        `-rs` on the pytest invocation, which prints every skip reason.
        """
        _restore_identity()
        message = (
            f"PostgreSQL fixture cannot use {PG_BASE_DSN} as {PG_TEST_USER}: {reason}"
        )
        if hard:
            pytest.fail(message, pytrace=False)
        pytest.skip(message)

    try:
        with psycopg.connect(PG_BASE_DSN, connect_timeout=10, autocommit=True) as conn:
            row = conn.execute(
                "SELECT system_identifier::text, pg_is_in_recovery() "
                "FROM pg_control_system()"
            ).fetchone()
            if row and row[0] == FLEET_SYSTEM_ID:
                if not row[1]:
                    # NOT in recovery -> the PRIMARY, where CREATE SCHEMA would
                    # SUCCEED. That is the only case worth failing over: the
                    # write lands in production.
                    _unusable(
                        f"that is the fleet PRIMARY (system_identifier={row[0]}). "
                        "Tests must never create schemas in production; point "
                        "SCITEX_WRITER_TEST_PG_DSN at a throwaway database.",
                        hard=True,
                    )
                # In recovery -> a read-only replica. Per the 2026-08-29 ruling
                # (one primary, all else read-only replicas) that is the
                # permanent shape of every host's loopback until CI provisions
                # its own database.
                _unusable(
                    "loopback is a read-only replica of the fleet cluster "
                    f"(system_identifier={row[0]}); there is no writable "
                    "database on this host",
                    hard=PG_REQUIRED or PG_DSN_WAS_DECLARED,
                )
            conn.execute(f'CREATE SCHEMA "{schema}"')
    except psycopg.errors.ReadOnlySqlTransaction as exc:
        # CONNECTED, but the server will not accept writes. psycopg models this
        # as InternalError, not OperationalError, so it must not be folded into
        # the handler below or the tests ERROR instead of skipping.
        _unusable(
            f"the server is a read-only replica ({exc})",
            hard=PG_REQUIRED or PG_DSN_WAS_DECLARED,
        )
    except psycopg.OperationalError as exc:
        # SKIP, not fail: not every machine that runs this suite has a local
        # cluster, and a test that DOES need PostgreSQL still must not fail on
        # a host that legitimately has none. Not silent, and not unconditional.
        _unusable(
            f"no reachable PostgreSQL ({exc})",
            hard=PG_REQUIRED or PG_DSN_WAS_DECLARED,
        )

    # BOTH variables, pointed at the same throwaway schema. The cards board is
    # not decoration here: a NON-EXISTENT explicit store makes `scitex_cards`
    # fall back to `$SCITEX_CARDS_DB` (measured 2026-08-29), so a tmp YAML path
    # cannot isolate the notify rail — only repointing the variable can.
    keys = ("SCITEX_STORE_DSN", _CARDS_DB_KEY)
    scoped = f"{PG_BASE_DSN}?options=-csearch_path%3D{schema}"
    saved = {key: os.environ.get(key) for key in keys}
    for key in keys:
        os.environ[key] = scoped
    try:
        yield schema
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
        # Wrapped so the identity restore happens even when the DROP raises: a
        # leaked PGUSER/PGPASSFILE does not fail here, it fails somewhere else
        # later as something that looks unrelated.
        try:
            with psycopg.connect(
                PG_BASE_DSN, connect_timeout=10, autocommit=True
            ) as conn:
                conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            _restore_identity()


@pytest.fixture()
def seed_card(pg_schema: str):
    """Seed one card on the THROWAWAY board; skip if that board has no schema.

    Returns ``seed(card_id, title) -> card_id``.

    `scitex_cards` refuses to write into a database that has no `tasks` table
    and exposes no public in-process provisioning verb (only the
    `scitex-cards init-store` CLI), so a fresh throwaway schema cannot host
    the notify rail. SKIPPING is the honest outcome, and it is not a coverage
    regression: what these tests did before was seed their fixture cards on
    the LIVE fleet board, which is not coverage anybody asked for.
    """
    pytest.importorskip("scitex_cards")
    from scitex_cards import add_task

    #: Store-shaped refusals, by class name so this file does not import
    #: scitex-cards internals — writer is a LEAF package and must not couple
    #: to them. Anything else re-raises: a fixture that swallows every error
    #: is a fixture that hides the bug it was written to catch.
    unprovisioned = {"StoreNotProvisionedError", "StoreUnavailableError"}

    def _seed(card_id: str, title: str) -> str:
        try:
            add_task(
                None,
                id=card_id,
                title=title,
                assignee="scitex-writer",
                created_by="scitex-writer",
            )
        except Exception as exc:  # noqa: BLE001 — narrowed by name, then re-raised
            if type(exc).__name__ in unprovisioned:
                pytest.skip(
                    f"the cards board in schema {pg_schema} has no tasks table "
                    f"and scitex-cards has no public provisioning verb: {exc}"
                )
            raise
        return card_id

    return _seed

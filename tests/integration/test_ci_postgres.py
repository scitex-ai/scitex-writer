"""Real leaf CI PostgreSQL lifecycle; server tools are a CI image dependency."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / ".github/ci/with-test-postgres.py"
PROBE = r"""
import json,os,sys,time
from pathlib import Path
import psycopg
with psycopg.connect(os.environ['SCITEX_WRITER_TEST_PG_DSN'], autocommit=True) as conn:
    with conn.cursor() as cursor:
        cursor.execute('CREATE TABLE fixture_write(value integer)')
        cursor.execute('INSERT INTO fixture_write VALUES (42)')
        cursor.execute('SELECT value FROM fixture_write')
        written=cursor.fetchone()[0]
        cursor.execute('SHOW data_directory')
        data=cursor.fetchone()[0]
        cursor.execute('SHOW listen_addresses')
        listening=cursor.fetchone()[0]
    result={'root':str(Path(data).parent),'written':written,'listen_addresses':listening,
            'required':os.environ['SCITEX_WRITER_TEST_PG_REQUIRED'],
            'store_is_private':os.environ['SCITEX_STORE_DSN']==os.environ['SCITEX_WRITER_TEST_PG_DSN'],
            'user':conn.info.user,'private_mode':Path(data).parent.stat().st_mode & 0o777}
    Path(sys.argv[1]).write_text(json.dumps(result))
    time.sleep(float(sys.argv[2]))
status=int(sys.argv[3])
if status < 0:
    os.kill(os.getpid(), -status)
raise SystemExit(status)
"""


def _command(report: Path, pause: int, status: int):
    return [
        sys.executable,
        str(DRIVER),
        "--",
        sys.executable,
        "-c",
        PROBE,
        str(report),
        str(pause),
        str(status),
    ]


@pytest.mark.parametrize(
    "status,expected_status",
    [(0, 0), (37, 37), (-signal.SIGTERM, 143)],
    ids=["success", "test-failure", "child-signal"],
)
def test_ci_postgres_preserves_child_status_and_removes_its_private_cluster(
    tmp_path, status, expected_status
):
    # Arrange
    report = tmp_path / "database.json"
    environment = {
        **os.environ,
        "SCITEX_STORE_DSN": "postgresql://must-not-connect.invalid/example",
        "PGPORT": "1",
        "PGHOSTADDR": "192.0.2.1",
    }
    # Act
    result = subprocess.run(
        _command(report, 0, status),
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    observed = json.loads(report.read_text())
    # Assert
    assert (
        result.returncode,
        observed["written"],
        observed["required"],
        observed["listen_addresses"],
        observed["store_is_private"],
        observed["user"],
        observed["private_mode"],
        Path(observed["root"]).exists(),
    ) == (expected_status, 42, "1", "", True, "postgres", 0o700, False)


def test_ci_postgres_cancellation_cleans_the_owned_database(tmp_path):
    # Arrange
    report = tmp_path / "database.json"
    process = subprocess.Popen(
        _command(report, 60, 0),
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Act
    try:
        deadline = time.monotonic() + 20
        while (
            not report.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        observed = json.loads(report.read_text())
        os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=20)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=10)
    # Assert
    assert (process.returncode, Path(observed["root"]).exists()) == (143, False)

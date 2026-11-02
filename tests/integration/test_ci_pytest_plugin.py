"""Real ordinary-CI pytest bootstrap: one private cluster across xdist workers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE = """import json,os
from pathlib import Path
import psycopg,pytest
@pytest.mark.parametrize("case", [1,2])
def test_private_store_is_required_and_writable(case):
    with psycopg.connect(os.environ["SCITEX_WRITER_TEST_PG_DSN"],autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE TABLE probe_{case}(value integer)")
            cursor.execute(f"INSERT INTO probe_{case} VALUES (42)")
            cursor.execute(f"SELECT value FROM probe_{case}"); value=cursor.fetchone()[0]
            cursor.execute("SHOW data_directory"); root=Path(cursor.fetchone()[0]).parent
            cursor.execute("SHOW listen_addresses"); listen=cursor.fetchone()[0]
        report={"root":str(root),"required":os.environ["SCITEX_WRITER_TEST_PG_REQUIRED"],"listen":listen,"value":value}
        Path(f"report-{case}.json").write_text(json.dumps(report))
    RESULT_CHECK
"""


@pytest.mark.parametrize(
    "workers,fail,expected_status",
    [(0, False, 0), (2, False, 0), (0, True, 1)],
    ids=["serial", "xdist", "pytest-failure"],
)
def test_ci_pytest_bootstrap_requires_one_private_cluster_and_cleans_it(
    tmp_path, workers, fail, expected_status
):
    # Arrange
    source = PROBE.replace(
        "RESULT_CHECK", "assert value == 99" if fail else "assert value == 42"
    )
    (tmp_path / "test_probe.py").write_text(source)
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / ".github/ci"),
        "PYTEST_ADDOPTS": "-p writer_ci_postgres",
    }
    for name in (
        "PYTEST_XDIST_WORKER",
        "SCITEX_WRITER_TEST_PG_DSN",
        "SCITEX_WRITER_TEST_PG_REQUIRED",
    ):
        environment.pop(name, None)
    # Act
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--noconftest",
            "-q",
            "-n",
            str(workers),
            "test_probe.py",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    reports = [json.loads(path.read_text()) for path in tmp_path.glob("report-*.json")]
    roots = {row["root"] for row in reports}
    observed = (
        result.returncode,
        len(reports),
        len(roots),
        all(
            row["required"] == "1" and row["listen"] == "" and row["value"] == 42
            for row in reports
        ),
        any(Path(root).exists() for root in roots),
    )
    # Assert
    assert observed == (expected_status, 2, 1, True, False), (
        result.stdout + result.stderr
    )

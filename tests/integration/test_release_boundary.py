"""Execute every actual release-control class in ordinary pytest test space.

Class granularity preserves each control and lets xdist schedule independent
owned resources. It intentionally replaces one aggregate 300s observation with
one 300s observation per class; production/cancellation deadlines do not change.
"""

import collections
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/ci/test_release_identity.py"
SPEC = importlib.util.spec_from_file_location("writer_native_release_controls", SCRIPT)
CONTROLS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CONTROLS
SPEC.loader.exec_module(CONTROLS)


def _cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _cases(item)
        else:
            yield item


def _identity(case):
    return type(case).__name__ + "." + case._testMethodName


CLASSES = sorted(
    (
        name,
        tuple(
            _identity(case)
            for case in _cases(unittest.defaultTestLoader.loadTestsFromTestCase(value))
        ),
    )
    for name, value in vars(CONTROLS).items()
    if isinstance(value, type) and issubclass(value, unittest.TestCase)
)
ALL_CASES = tuple(
    _identity(case)
    for case in _cases(unittest.defaultTestLoader.loadTestsFromModule(CONTROLS))
)


def test_class_discovery_covers_every_actual_release_control_once():
    # Arrange
    scheduled = [case for _, cases in CLASSES for case in cases]
    # Act
    observed = (collections.Counter(scheduled), len(scheduled), len(set(scheduled)))
    # Assert
    assert observed == (collections.Counter(ALL_CASES), len(ALL_CASES), len(ALL_CASES))


def _same_child(process, birth):
    current = CONTROLS.fixture_birth({"pid": process.pid})
    return (
        process.poll() is None
        and birth is not None
        and current is not None
        and current[0] == birth[0]
    )


def _owned_diagnostic(process):
    states = []
    pending = [process.pid]
    seen = set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        fields = CONTROLS.fixture_process_fields(pid)
        if fields is not None:
            states.append(
                {
                    "pid": pid,
                    "state": fields[0],
                    "ppid": fields[1],
                    "pgrp": fields[2],
                    "birth": fields[19],
                }
            )
            try:
                pending.extend(
                    map(
                        int,
                        Path(f"/proc/{pid}/task/{pid}/children").read_text().split(),
                    )
                )
            except (FileNotFoundError, ProcessLookupError):
                pass
    return states


@pytest.mark.parametrize(
    "control_class,expected_cases", CLASSES, ids=[name for name, _ in CLASSES]
)
def test_release_identity_archive_and_owned_process_controls(
    control_class, expected_cases
):
    # Arrange
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), control_class],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    birth = CONTROLS.fixture_birth({"pid": process.pid})
    # Act
    try:
        stdout, stderr = process.communicate(timeout=300)
    except subprocess.TimeoutExpired as failure:
        diagnostic = {
            "class": control_class,
            "owned_processes": _owned_diagnostic(process),
        }
        # Interrupt Python normally so its owned fixture finally blocks can run.
        # Escalation remains limited to this exact child's kernel birth/group.
        if _same_child(process, birth):
            os.kill(process.pid, signal.SIGINT)
        try:
            stdout, stderr = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            if _same_child(process, birth):
                os.killpg(process.pid, signal.SIGKILL)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired as secondary:
                stdout, stderr = secondary.output or b"", secondary.stderr or b""
                stdout = (
                    stdout.decode(errors="replace")
                    if isinstance(stdout, bytes)
                    else stdout
                )
                stderr = (
                    stderr.decode(errors="replace")
                    if isinstance(stderr, bytes)
                    else stderr
                )
                diagnostic["secondary_cleanup_timeout"] = True
        raise AssertionError(
            json.dumps(diagnostic) + "\n" + stdout + stderr
        ) from failure
    executed = [
        f"{owner}.{method}"
        for method, owner in re.findall(
            r"^(\w+) \(__main__\.(\w+)\.\w+\)", stderr, re.MULTILINE
        )
    ]
    count = re.search(r"^Ran (\d+) tests? in ", stderr, re.MULTILINE)
    observed = (
        process.returncode,
        collections.Counter(executed),
        int(count[1]) if count else None,
        bool(re.search(r"^OK$", stderr, re.MULTILINE)),
    )
    # Assert: exact case identities/count plus plain OK refuses skips or omissions.
    assert observed == (
        0,
        collections.Counter(expected_cases),
        len(expected_cases),
        True,
    ), stdout + stderr

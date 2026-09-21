"""Enforces SciTeX skills quality checklist §1–§4.
Canonical: src/scitex/_skills/general/21_scitex-package-quality-checklist.md
"""

from pathlib import Path

import pytest

# `_skills_quality_pytest` was introduced in a newer scitex-dev. Older peer
# installs (e.g. PyPI lag) don't ship it, so collect-time crashes CI. Skip
# gracefully when the helper is missing — same pattern as tests/integration/.
sq = pytest.importorskip(
    "scitex_dev._skills_quality_pytest",
    reason="requires scitex-dev with _skills_quality_pytest helper",
)

# PS-206b: import-smoke-allowed — the assertion lives inside the generated
# test body (make_skill_quality_tests returns a test function); this file
# only wires it to the package root.
test_skills_quality = sq.make_skill_quality_tests(
    package_root=Path(__file__).resolve().parents[1]
)

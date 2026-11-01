"""E2E: the CSV -> LaTeX table pipeline on real files via the real backend."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scitex_writer._utils._csv_table import render_csv_table

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("RUN_E2E") != "1",
        reason="e2e needs RUN_E2E=1 (real subsystems, slower than unit)",
    ),
]


def test_csv_renders_a_complete_latex_table_float(tmp_path: Path) -> None:
    # Arrange
    csv = tmp_path / "results.csv"
    csv.write_text("name,score\nalpha,0.5\nbeta,0.75\n", encoding="utf-8")
    # Act
    tex = render_csv_table(csv, caption="Results", label="tab:results")
    # Assert
    assert r"\begin{tabular}" in tex and r"\end{table}" in tex

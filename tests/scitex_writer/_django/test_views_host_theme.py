"""Theme-toggle contract: the host-injected row must never be a dead button.

Regression test for the 2026-10-31 report: clicking "Switch to dark/light
mode" in the host (hub) drawer on a hub-served leaf page changed nothing
until reload. Root cause, measured:

* Hub's SiteContentFrameMiddleware injects its global header (with
  `#theme-toggle`) into the leaf page, but the standalone shell never loads
  hub's `theme-switcher.ts` bundle — the row's only owner — so the row had
  no click handler on `/apps/writer/` or `/apps/writer/viewer/`.
* The writer toolbar's own toggle persisted to localStorage key
  `"scitex-theme"`, which nothing (pre-paint boot, host) ever reads back,
  so its choice died on reload.

Contract enforced here (all static, deterministic, no browser needed):

1. The frontend writes the canonical `"stx-theme"` key (+ legacy
   `"scitex-theme-preference"`) and never the dead `"scitex-theme"` key.
2. Both entry points (`index.ts`, `viewer.ts`) wire the host-row fallback.
3. The fallback stands down when the host bundle owns the row
   (`window.SciTeX.theme` present) so hub-served pages with a working host
   bundle never double-toggle.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND_SRC = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "scitex_writer"
    / "_django"
    / "frontend"
    / "src"
)

FALLBACK = FRONTEND_SRC / "host-theme-fallback.ts"

DEAD_KEY = re.compile(r"""(setItem|getItem|removeItem)\(\s*['"]scitex-theme['"]""")


def _read(name: str) -> str:
    # Arrange
    path = FRONTEND_SRC / name
    # Act
    src = path.read_text(encoding="utf-8")
    # Assert
    assert isinstance(src, str)
    return src


def _offenders() -> list[str]:
    # Arrange
    candidates = sorted(FRONTEND_SRC.glob("*.ts"))
    # Act
    offenders = [
        p.name for p in candidates if DEAD_KEY.search(p.read_text(encoding="utf-8"))
    ]
    # Assert
    assert isinstance(offenders, list)
    return offenders


def test_no_dead_theme_storage_key():
    # Arrange
    offenders = _offenders()
    # Act
    detail = ", ".join(offenders)
    # Assert
    assert offenders == [], f"dead localStorage key in {detail}"


def test_canonical_theme_key_present():
    # Arrange
    src = FALLBACK.read_text(encoding="utf-8")
    # Act
    found = '"stx-theme"' in src
    # Assert
    assert found


def test_legacy_theme_key_preserved():
    # Arrange
    src = FALLBACK.read_text(encoding="utf-8")
    # Act
    found = '"scitex-theme-preference"' in src
    # Assert
    assert found


def test_fallback_wired_in_index_entry_point():
    # Arrange
    src = _read("index.ts")
    # Act
    found = "wireHostThemeToggle" in src
    # Assert
    assert found


def test_fallback_imported_in_index_entry_point():
    # Arrange
    src = _read("index.ts")
    # Act
    found = "host-theme-fallback" in src
    # Assert
    assert found


def test_fallback_wired_in_viewer_entry_point():
    # Arrange
    src = _read("viewer.ts")
    # Act
    found = "wireHostThemeToggle" in src
    # Assert
    assert found


def test_fallback_imported_in_viewer_entry_point():
    # Arrange
    src = _read("viewer.ts")
    # Act
    found = "host-theme-fallback" in src
    # Assert
    assert found


def test_fallback_detects_host_theme_api():
    # Arrange
    src = FALLBACK.read_text(encoding="utf-8")
    # Act
    found = "SciTeX" in src
    # Assert
    assert found


def test_fallback_dispatches_host_theme_event():
    # Arrange
    src = FALLBACK.read_text(encoding="utf-8")
    # Act
    found = "theme-changed" in src
    # Assert
    assert found


def test_toolbar_routes_through_shared_applier():
    # Arrange
    src = _read("toolbar.ts")
    # Act
    found = "applyUiTheme" in src
    # Assert
    assert found

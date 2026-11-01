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
    Path(__file__).resolve().parents[4]
    / "src"
    / "scitex_writer"
    / "_django"
    / "frontend"
    / "src"
)

FALLBACK = FRONTEND_SRC / "host-theme-fallback.ts"


def _read(name: str) -> str:
    return (FRONTEND_SRC / name).read_text(encoding="utf-8")


def test_no_dead_theme_storage_key():
    """Nobody may read/write the write-only "scitex-theme" key (exact match)."""
    dead = re.compile(r"""(setItem|getItem|removeItem)\(\s*['"]scitex-theme['"]""")
    offenders = [
        p.name
        for p in FRONTEND_SRC.glob("*.ts")
        if dead.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        f"dead localStorage key 'scitex-theme' written in {offenders}; "
        "use THEME_STORAGE_KEY ('stx-theme') from host-theme-fallback.ts"
    )


def test_canonical_theme_keys_used():
    src = FALLBACK.read_text(encoding="utf-8")
    assert '"stx-theme"' in src
    assert '"scitex-theme-preference"' in src


def test_fallback_wired_in_both_entry_points():
    for entry in ("index.ts", "viewer.ts"):
        src = _read(entry)
        assert "wireHostThemeToggle" in src, f"{entry} never wires the fallback"
        assert "host-theme-fallback" in src, f"{entry} missing fallback import"


def test_fallback_stands_down_when_host_owns_row():
    src = FALLBACK.read_text(encoding="utf-8")
    assert "SciTeX" in src, "fallback must detect the host theme API"
    assert "theme-changed" in src, "fallback must dispatch the host event"


def test_toolbar_routes_through_shared_applier():
    src = _read("toolbar.ts")
    assert "applyUiTheme" in src

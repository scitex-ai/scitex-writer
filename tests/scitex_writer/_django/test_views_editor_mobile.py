#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_editor_mobile.py

"""Writer's phone layout: one pane at a time, a bottom action bar, 44px targets.

The scitex-ui shell stacks every pane vertically below 768px. That is right for
a workspace and wrong for writer — the section list, the editor and the PDF
became three full-height blocks in one column, so compiling from a phone meant
scrolling the editor off screen to reach the controls. Writer now swaps panes
itself, inside `.writer-app`, and keeps the desktop split untouched.

These are source-level assertions on purpose: what can be checked without a
browser is the structure (which pane each state selects, where the compile
button forwards to, whether a rule leaked out of the media query). The
measurement at 390x844 is the hub's site audit, not this file.
"""

import json
import re
import tempfile
from pathlib import Path

import pytest
from django.test import RequestFactory

from scitex_writer._django import views

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_MOBILE_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor-mobile.css"
_NARROW_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor-narrow-and-dock.css"
_MOBILE_TS = _DJANGO_DIR / "frontend" / "src" / "mobile.ts"
_SECTIONS_TS = _DJANGO_DIR / "frontend" / "src" / "sections.ts"
_INDEX_TS = _DJANGO_DIR / "frontend" / "src" / "index.ts"
_INDEX_JS = _DJANGO_DIR / "static" / "writer" / "assets" / "index.js"
_MANIFEST = _DJANGO_DIR / "manifest.json"

_MOBILE_QUERY = "@media (max-width: 768px)"


def _media_block(css: str, query: str) -> str:
    """The body of `query`'s block, braces balanced (nested blocks included)."""
    start = css.index(query)
    depth = 0
    for position in range(css.index("{", start), len(css)):
        depth += {"{": 1, "}": -1}.get(css[position], 0)
        if depth == 0:
            return css[start : position + 1]
    raise ValueError(f"unterminated block for {query}")


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_manuscript" / "contents").mkdir(parents=True)
        (root / "01_manuscript" / "contents" / "abstract.tex").write_text(
            "\\begin{abstract}x\\end{abstract}\n", encoding="utf-8"
        )
        (root / "00_shared").mkdir()
        yield root


def _editor_html(project_dir) -> str:
    request = RequestFactory().get(f"/?working_dir={project_dir}")
    return views.editor_page(request).content.decode()


# --- the page ships the layout ------------------------------------------------


def test_editor_page_loads_the_mobile_stylesheet(project_dir):
    # Arrange
    stylesheet = "writer/css/editor-mobile.css"
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert f'href="/static/{stylesheet}"' in body


def test_editor_page_renders_the_pane_switcher(project_dir):
    # Arrange
    panes = {"files", "editor", "preview"}
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert {m for m in re.findall(r'data-mobile-pane="(\w+)"', body)} == panes


def test_editor_page_renders_the_bottom_action_bar(project_dir):
    # Arrange
    controls = {"btn-mobile-save", "btn-mobile-log", "btn-mobile-compile"}
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert all(f'id="{control}"' in body for control in controls)


def test_editor_pane_is_the_one_marked_active_in_the_markup(project_dir):
    # Arrange
    editor_button = r'data-mobile-pane="editor"[^>]*aria-current="true"'
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert re.search(editor_button, body, re.S)


def test_pane_state_is_set_before_the_deferred_bundle_runs(project_dir):
    # Arrange
    body = _editor_html(project_dir)
    # Act
    inline = body.index('document.body.dataset.writerMobilePane = "editor"')
    bundle = body.index("writer/assets/index.js")
    # Assert
    assert inline < bundle


def test_mobile_layout_is_declared_in_the_manifest():
    # Arrange
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    # Act
    declared = manifest.get("mobile_layout")
    # Assert
    assert declared is True


def test_files_pane_mounts_the_shared_section_list(project_dir):
    # Arrange
    mount = 'id="writer-mobile-section-list"'
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert mount in body


# --- one pane at a time -------------------------------------------------------


def test_phone_layout_starts_from_every_pane_hidden():
    # Arrange
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    # Act
    hidden = _media_block(css, _MOBILE_QUERY)
    # Assert
    assert re.search(
        r"body\[data-writer-mobile-pane\]\s+\.writer-mobile-files,\s*"
        r"body\[data-writer-mobile-pane\]\s+\.writer-editor-pane,\s*"
        r"body\[data-writer-mobile-pane\]\s+\.writer-preview-pane\s*\{\s*"
        r"display:\s*none",
        hidden,
    )


def test_each_pane_value_restores_exactly_its_own_pane():
    # Arrange
    pairs = {
        "files": ".writer-mobile-files",
        "editor": ".writer-editor-pane",
        "preview": ".writer-preview-pane",
    }
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    # Act
    shown = _media_block(css, _MOBILE_QUERY)
    # Assert
    assert all(
        re.search(
            rf'body\[data-writer-mobile-pane="{pane}"\]\s+{re.escape(selector)}',
            shown,
        )
        for pane, selector in pairs.items()
    )


def test_the_desktop_chrome_is_absent_by_default():
    # Arrange
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    # Act
    outside = css[: css.index(_MOBILE_QUERY)]
    # Assert
    assert re.search(
        r"\.writer-mobile-panes,\s*\.writer-mobile-actions,\s*"
        r"\.writer-mobile-files\s*\{\s*display:\s*none",
        outside,
    )


def test_the_switcher_switches_that_state_on_click():
    # Arrange
    source = _MOBILE_TS.read_text(encoding="utf-8")
    # Act
    handler = source[source.index('querySelectorAll<HTMLButtonElement>("[data-mobile-pane]")') :]
    # Assert
    assert 'addEventListener("click", () => this.setPane(pane))' in handler


def test_the_switcher_does_not_hijack_touch_gestures():
    # Arrange
    source = _MOBILE_TS.read_text(encoding="utf-8")
    # Act
    gestures = re.findall(r'touch(start|move|end)|"swipe', source)
    # Assert
    assert gestures == []


def test_opening_a_section_returns_to_the_editor_pane():
    # Arrange
    source = _INDEX_TS.read_text(encoding="utf-8")
    # Act
    handler = source[source.index("void loadSection(section);") :]
    # Assert
    assert 'mobile.setPane("editor")' in handler[:400]


def test_section_click_and_selection_use_one_data_source():
    # Arrange
    source = _SECTIONS_TS.read_text(encoding="utf-8")
    # Act
    listed = source[source.index("private renderList()") :]
    # Assert
    assert "this.sections.forEach" in listed


# --- the bottom action bar ---------------------------------------------------


def test_touch_targets_meet_the_44px_minimum():
    # Arrange
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    # Act
    phone = _media_block(css, _MOBILE_QUERY)
    # Assert
    assert "--writer-touch-target-min: 44px" in phone


def test_action_bar_and_pane_buttons_use_the_shared_touch_target():
    # Arrange
    users = []
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    phone = _media_block(css, _MOBILE_QUERY)
    # Act
    for selector in (r"\.writer-mobile-action", r"\.writer-mobile-pane-btn"):
        users.append(
            re.search(
                rf"{selector}\s*\{{[^}}]*min-height:\s*var\(--writer-touch-target-min\)",
                phone,
            )
        )
    # Assert
    assert all(users)


def test_compile_forwards_to_the_single_compile_controller():
    # Arrange
    source = _MOBILE_TS.read_text(encoding="utf-8")
    # Act
    forwarded = 'this.compileBtn?.addEventListener("click", () => desktopCompileBtn?.click())'
    # Assert
    assert forwarded in source


def test_the_bar_does_not_reach_the_compile_api_directly():
    # Arrange
    source = _MOBILE_TS.read_text(encoding="utf-8")
    # Act
    calls = re.findall(r"api/compile|CompileController\(", source)
    # Assert
    assert calls == []


def test_save_takes_the_same_path_as_ctrl_s():
    # Arrange
    source = _INDEX_TS.read_text(encoding="utf-8")
    # Act
    wiring = source[source.index("onSave: () => {") :]
    # Assert
    assert "void flushSave();" in wiring[:300]


def test_compile_progress_is_mirrored_from_the_one_lamp():
    # Arrange
    source = _MOBILE_TS.read_text(encoding="utf-8")
    # Act
    mirror = source[source.index("private syncCompileButton") :]
    # Assert
    assert 'classList.contains("lamp-compiling")' in mirror


def test_action_bar_clears_the_hub_dock_and_the_home_bar():
    # Arrange
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    # Act
    phone = _media_block(css, _MOBILE_QUERY)
    rule = re.search(r"\.writer-mobile-actions\s*\{([^}]*)\}", phone).group(1)
    # Assert
    assert "--site-dock-clearance" in rule and "safe-area-inset-bottom" in rule


def test_the_pane_reserves_the_action_bars_height():
    # Arrange
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    # Act
    phone = _media_block(css, _MOBILE_QUERY)
    # Assert
    assert re.search(
        r"padding-bottom:\s*calc\(\s*var\(--writer-mobile-bar-height\)", phone
    )


# --- the PDF pane fits the width ---------------------------------------------


def test_entering_the_pdf_pane_fits_the_page_to_the_width():
    # Arrange
    source = _INDEX_TS.read_text(encoding="utf-8")
    # Act
    change = source[source.index("onPaneChange:") :]
    # Assert
    assert 'pane === "preview") pdf?.setFitWidth();' in change[:400]


def test_the_pdf_pane_cannot_overflow_its_container():
    # Arrange
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    # Act
    phone = _media_block(css, _MOBILE_QUERY)
    # Assert
    assert re.search(
        r'body\[data-writer-mobile-pane="preview"\]\s+\.writer-preview-pane,[^}]*'
        r"overflow-x:\s*hidden",
        phone,
    )


# --- the editor keeps its code width ----------------------------------------


def test_the_phone_editor_drops_the_glyph_margin_and_minimap():
    # Arrange
    source = _INDEX_TS.read_text(encoding="utf-8")
    # Act
    compact = source[source.index("function compactPhoneEditor()") :]
    # Assert
    assert 'minimap: { enabled: false }' in compact and "glyphMargin: false" in compact


def test_the_editor_is_relaid_out_when_its_pane_comes_back():
    # Arrange
    source = _INDEX_TS.read_text(encoding="utf-8")
    # Act
    change = source[source.index("onPaneChange:") :]
    # Assert
    assert "editor.getEditor()?.layout()" in change[:400]


# --- one breakpoint, and a rebuilt bundle ------------------------------------


def test_the_typescript_and_the_stylesheet_share_one_breakpoint():
    # Arrange
    source = _MOBILE_TS.read_text(encoding="utf-8")
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    # Act
    declared = re.search(r'MOBILE_BREAKPOINT = "\((max-width: \d+px)\)"', source)
    # Assert
    assert declared and f"@media ({declared.group(1)})" in css


def test_the_phone_toolbar_drops_the_controls_the_bar_owns():
    # Arrange
    owned_by_the_bar = [
        "#btn-compile",
        "#btn-toggle-log",
        "#btn-compile-mode",
    ]
    css = _MOBILE_CSS.read_text(encoding="utf-8")
    # Act
    phone = _media_block(css, _MOBILE_QUERY)
    hidden = [
        match.group(1)
        for match in re.finditer(
            r"body\[data-writer-mobile-pane\]([^{]*)\{\s*display:\s*none", phone
        )
    ]
    # Assert
    assert any(
        all(control in selector_list for control in owned_by_the_bar)
        for selector_list in hidden
    )


def test_the_narrow_toolbar_rule_still_wraps_at_768():
    # Arrange
    css = _NARROW_CSS.read_text(encoding="utf-8")
    # Act
    narrow = _media_block(css, _MOBILE_QUERY)
    # Assert
    assert re.search(r"\.writer-toolbar\s*\{[^}]*flex-wrap:\s*wrap", narrow)


def test_shipped_bundle_was_rebuilt_with_the_mobile_layout():
    # Arrange
    bundle = _INDEX_JS.read_text(encoding="utf-8")
    # Act
    mounted = re.findall(r"writer-mobile-panes|writerMobilePane", bundle)
    # Assert
    assert len(mounted) >= 2


# EOF

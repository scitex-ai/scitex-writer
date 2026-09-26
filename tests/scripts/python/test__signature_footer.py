#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: _signature_footer.py — the opt-in visible "Compiled by
# scitex-writer v<version>" page footer (feature toggle, default OFF).
#
# Style: no mocks (STX-NM002), one behavioral assert per test (STX-TQ007), no
# monkeypatch (PA-306), explicit AAA markers (STX-TQ002). Precedence is
# exercised with REAL config files under tmp_path + an injected `environ`
# mapping (env tiers) + an isolated HOME (user config tier), like
# tests/scripts/python/test__severity.py.

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from _signature_footer import (  # noqa: E402
    SIGNATURE_FOOTER_CONFIG_KEY,
    SIGNATURE_FOOTER_ENV,
    SIGNATURE_FOOTER_SENTINEL,
    build_footer_injection,
    resolve_signature_footer_enabled,
    resolve_writer_version,
)

# ============================================================================
# helpers / fixtures
# ============================================================================


@pytest.fixture
def isolated_home():
    """Isolate HOME (the user-config tier) so a real ~/.scitex config never
    leaks into the default-OFF assertions. Restores HOME afterwards."""
    saved = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as home:
        os.environ["HOME"] = home
        yield Path(home)
    if saved is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = saved


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _user_config(home, text):
    _write(home / ".scitex" / "writer" / "config.yaml", text)


# ============================================================================
# precedence ladder: CLI > env > project ./config.yaml > user config > default
# ============================================================================


def test_default_is_off(tmp_path, isolated_home):
    """Nothing set anywhere -> the footer defaults OFF."""
    # Arrange
    environ = {}
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ=environ)
    # Assert
    assert result is False


def test_cli_flag_forces_on(tmp_path, isolated_home):
    """The CLI flag (opt-in) turns the footer ON regardless of config."""
    # Arrange
    environ = {}
    # Act
    result = resolve_signature_footer_enabled(True, tmp_path, environ=environ)
    # Assert
    assert result is True


def test_env_true_enables(tmp_path, isolated_home):
    """A truthy env var turns the footer ON."""
    # Arrange
    environ = {SIGNATURE_FOOTER_ENV: "true"}
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ=environ)
    # Assert
    assert result is True


def test_env_false_disables(tmp_path, isolated_home):
    """A falsy env var keeps the footer OFF."""
    # Arrange
    environ = {SIGNATURE_FOOTER_ENV: "false"}
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ=environ)
    # Assert
    assert result is False


def test_project_config_true_enables(tmp_path, isolated_home):
    """project ./config.yaml `signature_footer: true` turns the footer ON."""
    # Arrange
    pytest.importorskip("yaml")
    _write(tmp_path / "config.yaml", "signature_footer: true\n")
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ={})
    # Assert
    assert result is True


def test_project_config_false_disables(tmp_path, isolated_home):
    """project ./config.yaml `signature_footer: false` keeps the footer OFF."""
    # Arrange
    pytest.importorskip("yaml")
    _write(tmp_path / "config.yaml", "signature_footer: false\n")
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ={})
    # Assert
    assert result is False


def test_user_config_true_enables(tmp_path, isolated_home):
    """user ~/.scitex/writer/config.yaml is the global opt-in tier."""
    # Arrange
    pytest.importorskip("yaml")
    _user_config(isolated_home, "signature_footer: true\n")
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ={})
    # Assert
    assert result is True


def test_env_beats_project_config(tmp_path, isolated_home):
    """env (higher tier) overrides project ./config.yaml (lower tier)."""
    # Arrange
    pytest.importorskip("yaml")
    _write(tmp_path / "config.yaml", "signature_footer: true\n")
    environ = {SIGNATURE_FOOTER_ENV: "false"}
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ=environ)
    # Assert
    assert result is False


def test_project_config_beats_user_config(tmp_path, isolated_home):
    """project ./config.yaml overrides user ~/.scitex/writer/config.yaml."""
    # Arrange
    pytest.importorskip("yaml")
    _write(tmp_path / "config.yaml", "signature_footer: false\n")
    _user_config(isolated_home, "signature_footer: true\n")
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ={})
    # Assert
    assert result is False


def test_cli_flag_beats_env_false(tmp_path, isolated_home):
    """The CLI opt-in wins over an env var set to false."""
    # Arrange
    environ = {SIGNATURE_FOOTER_ENV: "false"}
    # Act
    result = resolve_signature_footer_enabled(True, tmp_path, environ=environ)
    # Assert
    assert result is True


def test_yaml_off_token_disables(tmp_path, isolated_home):
    """A bare YAML `off` (coerced to False by PyYAML) keeps the footer OFF."""
    # Arrange
    pytest.importorskip("yaml")
    _write(tmp_path / "config.yaml", "signature_footer: off\n")
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ={})
    # Assert
    assert result is False


def test_config_key_is_the_ssot_constant(tmp_path, isolated_home):
    """The config key resolves via the SSoT constant (rename-safe)."""
    # Arrange
    pytest.importorskip("yaml")
    _write(tmp_path / "config.yaml", f"{SIGNATURE_FOOTER_CONFIG_KEY}: true\n")
    # Act
    result = resolve_signature_footer_enabled(False, tmp_path, environ={})
    # Assert
    assert result is True


# ============================================================================
# version resolution (mirrors the pdfcreator metadata resolution)
# ============================================================================


def test_version_from_env(tmp_path):
    """SCITEX_WRITER_VERSION (exported by load_config.sh) is used first."""
    # Arrange
    environ = {"SCITEX_WRITER_VERSION": "3.1.4"}
    # Act
    result = resolve_writer_version(environ=environ, repo_root=tmp_path)
    # Assert
    assert result == "3.1.4"


def test_version_env_unknown_falls_through(tmp_path):
    """A literal 'unknown' env value is ignored (falls through to files)."""
    # Arrange
    _write(tmp_path / "VERSION", "7.7.7\n")
    environ = {"SCITEX_WRITER_VERSION": "unknown"}
    # Act
    result = resolve_writer_version(environ=environ, repo_root=tmp_path)
    # Assert
    assert result == "7.7.7"


def test_version_from_version_file(tmp_path):
    """A repo-root VERSION file is read when the env var is absent."""
    # Arrange
    _write(tmp_path / "VERSION", "2.9.0\n")
    # Act
    result = resolve_writer_version(environ={}, repo_root=tmp_path)
    # Assert
    assert result == "2.9.0"


def test_version_from_pyproject(tmp_path):
    """pyproject.toml [project] version is the final real source."""
    # Arrange
    _write(tmp_path / "pyproject.toml", 'version = "5.6.7"\n')
    # Act
    result = resolve_writer_version(environ={}, repo_root=tmp_path)
    # Assert
    assert result == "5.6.7"


def test_version_unknown_when_nothing_available(tmp_path):
    """No env, no VERSION, no pyproject -> 'unknown'."""
    # Arrange
    environ = {}
    # Act
    result = resolve_writer_version(environ=environ, repo_root=tmp_path)
    # Assert
    assert result == "unknown"


# ============================================================================
# preamble injection: right snippet emitted when ON, nothing when style missing
# ============================================================================


def _write_style(styles_dir):
    _write(
        styles_dir / "signature_footer.tex",
        "% footer style\nCompiled by SciTeX Writer v__SCITEX_WRITER_VERSION__\n",
    )


def test_injection_substitutes_version(tmp_path):
    """The version placeholder is replaced with the resolved version."""
    # Arrange
    _write_style(tmp_path)
    # Act
    injection = build_footer_injection(tmp_path, "4.2.0")
    # Assert
    assert "Compiled by SciTeX Writer v4.2.0" in injection


def test_injection_carries_sentinel(tmp_path):
    """The injected block starts with the idempotency sentinel."""
    # Arrange
    _write_style(tmp_path)
    # Act
    injection = build_footer_injection(tmp_path, "4.2.0")
    # Assert
    assert SIGNATURE_FOOTER_SENTINEL in injection


def test_injection_leaves_no_placeholder(tmp_path):
    """No unsubstituted placeholder token survives in the injected block."""
    # Arrange
    _write_style(tmp_path)
    # Act
    injection = build_footer_injection(tmp_path, "4.2.0")
    # Assert
    assert "__SCITEX_WRITER_VERSION__" not in injection


def test_injection_empty_when_style_missing(tmp_path):
    """A missing style file yields '' (fail-safe: never abort a compile)."""
    # Arrange
    missing_styles_dir = tmp_path
    # Act
    injection = build_footer_injection(missing_styles_dir, "4.2.0")
    # Assert
    assert injection == ""


# ============================================================================
# end-to-end flattener gating: footer present when ON, absent when OFF
# ============================================================================


def _make_project(tmp_path):
    """Minimal <root>/doc/base.tex + <root>/00_shared/latex_styles project."""
    styles = tmp_path / "00_shared" / "latex_styles"
    real_style = ROOT_DIR / "00_shared" / "latex_styles" / "signature_footer.tex"
    _write(styles / "signature_footer.tex", real_style.read_text(encoding="utf-8"))
    base_tex = tmp_path / "doc" / "base.tex"
    _write(base_tex, "\\documentclass{article}\n\\begin{document}\nHi\\end{document}\n")
    return base_tex


def _flatten(base_tex, out_tex, *, signature_footer):
    import compile_tex_structure as cts

    saved = os.environ.get("SCITEX_WRITER_PROJECT_ROOT")
    os.environ["SCITEX_WRITER_PROJECT_ROOT"] = str(base_tex.parent.parent)
    try:
        cts.compile_tex_structure(
            base_tex=base_tex,
            output_tex=out_tex,
            verbose=False,
            signature_footer=signature_footer,
        )
    finally:
        if saved is None:
            os.environ.pop("SCITEX_WRITER_PROJECT_ROOT", None)
        else:
            os.environ["SCITEX_WRITER_PROJECT_ROOT"] = saved


def test_flatten_injects_footer_when_on(tmp_path):
    """signature_footer=True -> the footer block lands in the flattened TeX."""
    # Arrange
    base_tex = _make_project(tmp_path)
    out_tex = tmp_path / "out.tex"
    # Act
    _flatten(base_tex, out_tex, signature_footer=True)
    # Assert
    assert SIGNATURE_FOOTER_SENTINEL in out_tex.read_text(encoding="utf-8")


def test_flatten_omits_footer_when_off(tmp_path):
    """signature_footer=False -> default compile is unchanged (no footer)."""
    # Arrange
    base_tex = _make_project(tmp_path)
    out_tex = tmp_path / "out.tex"
    # Act
    _flatten(base_tex, out_tex, signature_footer=False)
    # Assert
    assert SIGNATURE_FOOTER_SENTINEL not in out_tex.read_text(encoding="utf-8")


# ============================================================================
# redesign A/B: bottom-right anchor + clew-signature-toggle drives the footer
# ============================================================================


def test_real_footer_style_is_anchored_bottom_right(tmp_path):
    """The shipped footer style anchors its TikZ node at the page south-east."""
    # Arrange
    real_style = ROOT_DIR / "00_shared" / "latex_styles" / "signature_footer.tex"
    _write(tmp_path / "signature_footer.tex", real_style.read_text(encoding="utf-8"))
    # Act
    injection = build_footer_injection(tmp_path, "4.2.0")
    # Assert
    assert "anchor=south east" in injection


def test_real_footer_style_positions_at_page_south_east(tmp_path):
    """The node is placed relative to `current page.south east` (not .south)."""
    # Arrange
    real_style = ROOT_DIR / "00_shared" / "latex_styles" / "signature_footer.tex"
    _write(tmp_path / "signature_footer.tex", real_style.read_text(encoding="utf-8"))
    # Act
    injection = build_footer_injection(tmp_path, "4.2.0")
    # Assert
    assert "current page.south east" in injection


def _make_project_with_preamble(tmp_path, preamble):
    """Minimal project whose base.tex carries an extra preamble line."""
    styles = tmp_path / "00_shared" / "latex_styles"
    real_style = ROOT_DIR / "00_shared" / "latex_styles" / "signature_footer.tex"
    _write(styles / "signature_footer.tex", real_style.read_text(encoding="utf-8"))
    base_tex = tmp_path / "doc" / "base.tex"
    _write(
        base_tex,
        "\\documentclass{article}\n"
        + preamble
        + "\n\\begin{document}\nHi\\end{document}\n",
    )
    return base_tex


def test_clew_signature_toggle_triggers_footer(tmp_path):
    """clew `signature` toggle ON (opt-in OFF) still injects the footer."""
    # Arrange
    base_tex = _make_project_with_preamble(tmp_path, "\\clewpressignaturetrue")
    out_tex = tmp_path / "out.tex"
    # Act
    _flatten(base_tex, out_tex, signature_footer=False)
    # Assert
    assert SIGNATURE_FOOTER_SENTINEL in out_tex.read_text(encoding="utf-8")


def test_footer_injected_once_when_both_sources_on(tmp_path):
    """DRY: opt-in AND clew signature toggle both ON -> the block appears once."""
    # Arrange
    base_tex = _make_project_with_preamble(tmp_path, "\\clewpressignaturetrue")
    out_tex = tmp_path / "out.tex"
    # Act
    _flatten(base_tex, out_tex, signature_footer=True)
    # Assert
    assert out_tex.read_text(encoding="utf-8").count(SIGNATURE_FOOTER_SENTINEL) == 1


# EOF

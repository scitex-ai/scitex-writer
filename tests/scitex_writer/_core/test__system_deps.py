#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: src/scitex_writer/_core/_system_deps.py

import pytest

from scitex_writer._core._system_deps import _PACKAGES, APT_PACKAGES, _main


def test_apt_packages_nonempty():
    # Arrange
    # Act
    # Assert
    assert APT_PACKAGES


def test_apt_packages_has_core_latex():
    # Arrange
    # Act
    # Assert
    assert "texlive-latex-base" in APT_PACKAGES


def test_apt_packages_has_parallel():
    # Arrange
    # Act
    # Assert
    assert "parallel" in APT_PACKAGES


def test_apt_packages_has_poppler_for_the_artifact_gate():
    # Arrange
    # Act
    # Assert: the post-compile gate's pdfimages/pdftotext/pdfinfo checks
    # WARN-skip without it, so a host built from this list must carry it.
    assert "poppler-utils" in APT_PACKAGES


def test_apt_packages_has_both_bibtex_and_biber():
    # Arrange
    # Act
    # Assert: keep-both -- bibtex is the default natbib path, biber lets
    # biblatex-based projects compile (neurovista coordination, 2026-06-26).
    assert {"texlive-bibtex-extra", "biber"} <= set(APT_PACKAGES)


def test_apt_packages_match_package_table():
    # Arrange
    expected = [pkg for pkg, _ in _PACKAGES]
    # Act
    # Assert
    assert APT_PACKAGES == expected


def test_main_emits_one_package_per_line(capsys):
    # Arrange
    # Act
    _main()
    # Assert
    assert capsys.readouterr().out.splitlines() == APT_PACKAGES


def test_provide_tags_every_dep_with_writer_provider():
    # Arrange
    pytest.importorskip("scitex_dev.system_deps")
    from scitex_writer._core._system_deps import provide

    # Act
    specs = provide()
    # Assert
    assert all(s.provider == "scitex-writer" for s in specs)

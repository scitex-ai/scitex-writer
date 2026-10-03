#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: src/scitex_writer/_django/settings.py

"""Settings must only reference symbols the INSTALLED dependencies provide.

Why this file exists: writer pinned `scitex-ui>=0.1.0` while settings.py
registered `scitex_ui.context_processors.element_inspector` — a module that
does not exist before scitex-ui 0.5.x. pip therefore resolved 0.4.5 happily
and the editor 500'd at RENDER time with ModuleNotFoundError. The dependency
floor was a promise the code had already outgrown, and nothing checked it.

These tests import every context processor settings names, so a floor that is
too low fails HERE (loudly, in CI, on a fresh [dev] install) instead of in the
operator's browser.
"""

import importlib
import importlib.util

import pytest

from .conftest import _init_django

_init_django()

from django.conf import settings  # noqa: E402


def _context_processor_paths() -> list[str]:
    return settings.TEMPLATES[0]["OPTIONS"]["context_processors"]


@pytest.mark.parametrize("dotted_path", _context_processor_paths())
def test_every_context_processor_is_importable(dotted_path):
    # Arrange
    module_path, _, attr = dotted_path.rpartition(".")
    # Act
    module = importlib.import_module(module_path)
    # Assert
    assert hasattr(module, attr)


def test_sdk_ui_context_processors_module_exists():
    # Arrange
    name = "scitex_sdk.ui.context_processors"
    # Act
    spec = importlib.util.find_spec(name)
    # Assert
    assert spec is not None

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
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from .conftest import _init_django

_init_django()

from django.conf import settings  # noqa: E402
from scitex_writer._django import settings as local_settings  # noqa: E402


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


@pytest.fixture
def local_database_configuration(tmp_path):
    """Observe the real settings before and after Django's dummy normalization."""
    program = r'''
import json
import sys

def refuse_database(frame, event, argument):
    path = frame.f_code.co_filename.replace("\\", "/")
    if event == "call" and "/django/db/backends/" in path:
        if frame.f_code.co_name in {"connect", "get_new_connection"}:
            raise RuntimeError("database connection refused")

sys.setprofile(refuse_database)
from scitex_writer._django import settings as local_settings
declared = json.loads(json.dumps(local_settings.DATABASES))
import django
django.setup()
from django.db import connections
normalized = {name: item["ENGINE"] for name, item in connections.settings.items()}
print("DATABASE_CONFIGURATION=" + json.dumps({"declared": declared, "normalized": normalized}))
'''
    environment = dict(os.environ)
    environment.update(
        DJANGO_SETTINGS_MODULE="scitex_writer._django.settings",
        PYTHONPATH=str(Path(__file__).resolve().parents[3] / "src")
        + os.pathsep + environment.get("PYTHONPATH", ""),
        PYTHONDONTWRITEBYTECODE="1",
        SCITEX_DIR=str(tmp_path / "scitex-runtime"),
        TMPDIR=str(tmp_path),
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    line = next(
        line for line in completed.stdout.splitlines()
        if line.startswith("DATABASE_CONFIGURATION=")
    )
    return json.loads(line.partition("=")[2])


def test_local_settings_do_not_select_a_database(local_database_configuration):
    # Arrange
    configured = local_database_configuration
    # Act
    databases = configured["declared"]
    # Assert
    assert databases == {}


def test_django_normalizes_the_modelless_database_to_dummy(local_database_configuration):
    # Arrange
    configured = local_database_configuration
    # Act
    engines = configured["normalized"]
    # Assert
    assert engines == {"default": "django.db.backends.dummy"}


def test_local_settings_use_the_existing_standalone_provider():
    # Arrange
    configured = local_settings
    # Act
    provider = configured.SCITEX_PROJECT_PROVIDER
    # Assert
    assert provider == "scitex_sdk.app.project_context.StandaloneProjectProvider"


def test_local_settings_activate_real_browser_language():
    # Arrange
    configured = local_settings
    # Act
    middleware = configured.MIDDLEWARE
    # Assert
    assert "django.middleware.locale.LocaleMiddleware" in middleware


def test_locale_middleware_precedes_common_middleware():
    # Arrange
    middleware = local_settings.MIDDLEWARE
    # Act
    positions = (
        middleware.index("django.middleware.locale.LocaleMiddleware"),
        middleware.index("django.middleware.common.CommonMiddleware"),
    )
    # Assert
    assert positions[0] < positions[1]


def test_local_template_context_receives_the_registered_project_provider():
    # Arrange
    configured = local_settings
    # Act
    paths = configured.TEMPLATES[0]["OPTIONS"]["context_processors"]
    # Assert
    assert "scitex_writer._django.context_processors.project_context" in paths


def test_local_settings_retain_csrf_protection():
    # Arrange
    configured = local_settings
    # Act
    middleware = configured.MIDDLEWARE
    # Assert
    assert "django.middleware.csrf.CsrfViewMiddleware" in middleware

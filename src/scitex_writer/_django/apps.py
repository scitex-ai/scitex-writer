#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import warnings

from ._workspace_shell import REMEDY, probe_missing_shell

try:
    from scitex_sdk import app as _sdk_app
except ImportError:
    # Falling back to a plain Django AppConfig means the editor loses the
    # scitex-app workspace shell. That is a real downgrade, so SAY SO — a
    # silent base-class swap left the editor looking installed and behaving
    # differently, with nothing to explain why.
    from django.apps import AppConfig as ScitexAppConfig

    warnings.warn(
        f"{probe_missing_shell()}: the writer editor is running without "
        f"the workspace shell. Get it with: {REMEDY}",
        RuntimeWarning,
        stacklevel=2,
    )
else:
    ScitexAppConfig = _sdk_app.embed.ScitexAppConfig


class WriterEditorConfig(ScitexAppConfig):
    name = "scitex_writer._django"
    label = "writer_editor"
    verbose_name = "SciTeX Writer Editor"

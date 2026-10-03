#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Writer's SDK plugin metadata is part of the base package contract."""

from scitex_sdk import app


class WriterEditorConfig(app.embed.ScitexAppConfig):
    name = "scitex_writer._django"
    label = "writer_editor"
    verbose_name = "SciTeX Writer Editor"

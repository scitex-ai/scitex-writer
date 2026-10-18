#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Django app exposing the scitex-writer editor (and viewer in PR2).

Consumed by scitex-cloud's `writer_app` as a thin wrapper — mirrors the
figrecipe/_django pattern so a single canonical implementation drives both
local-dev (`scitex-writer gui`) and cloud deployments.
"""

default_app_config = "scitex_writer._django.apps.WriterEditorConfig"

# Typed leaf declarations consumed by the generic workspace plugin loader.
context_builder = "scitex_writer._django.hosting.build_context"
partial_template = "writer/editor_partial.html"
content_renderer = "scitex_writer._django.hosting.render_content"
api_policy_module = "scitex_writer._django._host_boundary"
hosted_api_dispatcher = "scitex_writer._django.views.api_dispatch"

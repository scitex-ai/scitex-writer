#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""URL patterns for the scitex-writer editor Django app."""

from django.urls import path

from . import views
from .sections import manuscript_status, section_content

app_name = "writer"

urlpatterns = [
    path("", views.editor_page, name="editor"),
    path("viewer/", views.viewer_page, name="viewer"),
    path("editor-v2/", views.editor_v2_page, name="writer_v2_editor"),
    path("viewer-v2/", views.viewer_v2_page, name="writer_v2_viewer"),
    path(
        "v2/api/project/<int:project_id>/section/<path:section_name>/",
        section_content,
        name="writer_v2_api_section",
    ),
    path(
        "v2/api/project/<int:project_id>/manuscript-status/",
        manuscript_status,
        name="writer_v2_api_manuscript_status",
    ),
    path("v2/<path:endpoint>", views.api_dispatch, name="writer_v2_api"),
    path(
        "api/project/<int:project_id>/section/<path:section_name>/",
        section_content,
        name="api_section",
    ),
    path(
        "api/project/<int:project_id>/manuscript-status/",
        manuscript_status,
        name="api_manuscript_status",
    ),
    path("<path:endpoint>", views.api_dispatch, name="api"),
]

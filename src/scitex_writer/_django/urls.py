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

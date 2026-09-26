#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The HTTP compile endpoint records its REFUSALS in the workspace event log.

These are the cases where writer never started the engine because the
request itself was declined -- wrong verb, a compile already running. Each
must leave a `refusal` record with its own reason, distinguishable from any
compile failure, without the browser being the only witness.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("django")
from django.test import RequestFactory  # noqa: E402

from scitex_writer._compile._event_log import EVENT_REFUSAL, read_events  # noqa: E402
from scitex_writer._django.handlers.compile import handle_compile  # noqa: E402
from scitex_writer._django.services import ProjectState  # noqa: E402


@pytest.fixture
def project(tmp_path):
    return ProjectState(project_dir=tmp_path)


@pytest.fixture
def busy_project(project):
    project._compiling = True
    return project


def _post(body: dict):
    return RequestFactory().post(
        "/api/compile", data=json.dumps(body), content_type="application/json"
    )


class TestBusy:
    def test_busy_project_is_refused_with_409(self, busy_project):
        # Arrange
        request = _post({"doc_type": "manuscript"})
        # Act
        resp = handle_compile(request, busy_project)
        # Assert
        assert resp.status_code == 409

    def test_busy_refusal_lands_in_the_log(self, busy_project):
        # Arrange
        request = _post({"doc_type": "manuscript"})
        # Act
        handle_compile(request, busy_project)
        # Assert
        assert [e["kind"] for e in read_events(busy_project.project_dir)] == [
            EVENT_REFUSAL
        ]

    def test_busy_refusal_names_its_reason(self, busy_project):
        # Arrange
        request = _post({"doc_type": "manuscript"})
        # Act
        handle_compile(request, busy_project)
        # Assert
        assert read_events(busy_project.project_dir)[-1]["reason"] == "busy"

    def test_busy_refusal_names_the_django_entry_point(self, busy_project):
        # Arrange
        request = _post({"doc_type": "manuscript"})
        # Act
        handle_compile(request, busy_project)
        # Assert
        assert read_events(busy_project.project_dir)[-1]["entry_point"] == "django"


class TestWrongVerb:
    def test_get_is_refused_with_405(self, project):
        # Arrange
        request = RequestFactory().get("/api/compile")
        # Act
        resp = handle_compile(request, project)
        # Assert
        assert resp.status_code == 405

    def test_get_refusal_lands_in_the_log_with_its_reason(self, project):
        # Arrange
        request = RequestFactory().get("/api/compile")
        # Act
        handle_compile(request, project)
        # Assert
        assert read_events(project.project_dir)[-1]["reason"] == "method-not-allowed"


# EOF

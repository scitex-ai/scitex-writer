"""Real SDK rendering reads project context without repeating navigation."""

from __future__ import annotations

import pytest
from django.test import RequestFactory, override_settings
from scitex_sdk.app.project_context import CHANGE_PROJECT_COMMAND
from scitex_sdk.ui.project_scope import ProjectEntry

from .conftest import _init_django

_init_django()

from scitex_writer._django.context_processors import project_context  # noqa: E402


class Projects:
    """Synthetic in-memory provider implementing the genuine SDK protocol."""

    def __init__(self):
        self.selected = "17"
        self.remembered = []

    def list_projects(self, request):
        return [ProjectEntry("17", "Alpha"), ProjectEntry("21", "Beta")]

    def last_visited(self, request):
        return self.selected

    def remember(self, request, project_id):
        self.selected = project_id
        self.remembered.append(project_id)


projects = Projects()


@pytest.fixture
def registered_provider():
    global projects
    projects = Projects()
    with override_settings(
        SCITEX_PROJECT_PROVIDER=__name__ + ".projects",
        SCITEX_PROJECT_PROVIDER_URL="/platform/api/project-scope",
    ):
        yield projects


@pytest.mark.parametrize("mode", ["hub", "standalone"])
def test_rendering_keeps_the_prior_navigation_selection(registered_provider, mode):
    # Arrange
    provider = registered_provider
    request = RequestFactory().get("/", {"project": "21"})
    # Act
    with override_settings(SCITEX_APP_MODE=mode):
        project_context(request)
    # Assert
    assert (provider.selected, provider.remembered) == ("17", [])


@pytest.mark.parametrize("mode", ["hub", "standalone"])
def test_rendering_retains_the_sdk_context_contract(registered_provider, mode):
    # Arrange
    request = RequestFactory().get("/", {"project": "21"})
    # Act
    with override_settings(SCITEX_APP_MODE=mode):
        context = project_context(request)
    # Assert
    assert context == {
        "active_project": {"id": "21", "name": "Beta"},
        "project_state": "ok",
        "project_command": CHANGE_PROJECT_COMMAND,
        "project_provider_endpoint": "/platform/api/project-scope",
    }


@pytest.mark.parametrize("mode", ["hub", "standalone"])
def test_rendering_keeps_inaccessible_projects_denied(registered_provider, mode):
    # Arrange
    provider = registered_provider
    request = RequestFactory().get("/", {"project": "not-authorized"})
    # Act
    with override_settings(SCITEX_APP_MODE=mode):
        context = project_context(request)
    # Assert
    assert (context["project_state"], context["active_project"], provider.selected, provider.remembered) == (
        "denied", None, "17", []
    )


@pytest.mark.parametrize("mode", ["hub", "standalone"])
def test_rendering_without_a_selector_observes_the_stored_project(registered_provider, mode):
    # Arrange
    provider = registered_provider
    request = RequestFactory().get("/")
    # Act
    with override_settings(SCITEX_APP_MODE=mode):
        context = project_context(request)
    # Assert
    assert (context["active_project"], provider.remembered) == ({"id": "17", "name": "Alpha"}, [])


def test_rendering_keeps_an_absent_provider_unavailable():
    # Arrange
    request = RequestFactory().get("/", {"project": "21"})
    # Act
    with override_settings(SCITEX_PROJECT_PROVIDER=""):
        context = project_context(request)
    # Assert
    assert (context["project_state"], context["active_project"]) == ("unavailable", None)

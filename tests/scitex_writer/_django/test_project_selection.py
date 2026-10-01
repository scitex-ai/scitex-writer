"""Late resource requests stay scoped without changing newer navigation."""

from types import SimpleNamespace

import pytest
from django.test import Client, override_settings
from django.urls import include, path
from scitex_sdk.ui import project_scope

from scitex_writer._django import services


class SessionIdentity:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = SimpleNamespace(
            is_authenticated=bool(request.headers.get("Selection-Session"))
        )
        return self.get_response(request)


class Projects:
    def __init__(self):
        self.selected = "17"
        self.remembered = []

    def list_projects(self, request):
        return [
            project_scope.ProjectEntry("17", "Alpha"),
            project_scope.ProjectEntry("21", "Beta"),
        ]

    def last_visited(self, request):
        return self.selected

    def remember(self, request, project_id):
        self.selected = project_id
        self.remembered.append(project_id)


projects = Projects()
urlpatterns = [path("plugin/writer/", include("scitex_writer._django.urls"))]


@pytest.fixture
def mounted(tmp_path):
    global projects
    projects = Projects()
    roots = {}
    for key, label in [("17", "alpha"), ("21", "beta")]:
        root = tmp_path / label
        workspace = root / ".scitex/writer"
        (workspace / "00_shared").mkdir(parents=True)
        (workspace / "01_manuscript/contents").mkdir(parents=True)
        (workspace / "02_supplementary/contents").mkdir(parents=True)
        (workspace / "03_revision/contents").mkdir(parents=True)
        (workspace / "01_manuscript/contents/abstract.tex").write_text(
            f"Synthetic {label} abstract.", encoding="utf-8"
        )
        roots[key] = root
    storage = SimpleNamespace(
        project_path=lambda key, request: roots.get(key),
        can_write=lambda key, request: True,
    )
    services._project_cache.clear()
    with override_settings(
        SCITEX_APP_MODE="hub",
        ROOT_URLCONF=__name__,
        ALLOWED_HOSTS=["testserver"],
        MIDDLEWARE=[__name__ + ".SessionIdentity"],
        SCITEX_PROJECT_PROVIDER=__name__ + ".projects",
        SCITEX_PROJECT_STORAGE=storage,
    ):
        yield Client(enforce_csrf_checks=True), roots
    services._project_cache.clear()


def choose_beta(client):
    response = client.get(
        "/plugin/writer/?project=21", HTTP_SELECTION_SESSION="synthetic"
    )
    assert response.status_code == 200
    assert projects.selected == "21" and projects.remembered == ["21"]
    projects.remembered.clear()
    return client.cookies["csrftoken"].value


@pytest.mark.parametrize(
    "url",
    [
        "/plugin/writer/api/project-info?project=17",
        "/plugin/writer/api/project/17/section/abstract/",
        "/plugin/writer/api/project/17/manuscript-status/",
    ],
)
def test_late_alpha_resource_read_keeps_selected_beta(mounted, url):
    client, roots = mounted
    choose_beta(client)
    response = client.get(url, HTTP_SELECTION_SESSION="synthetic")
    assert response.status_code == 200
    data = response.json()
    if "content" in data:
        assert data["content"] == "Synthetic alpha abstract."
    elif "project_dir" in data:
        assert data["project_dir"] == str(roots["17"] / ".scitex/writer")
    else:
        assert data["exists"] is True
    assert projects.selected == "21" and projects.remembered == []


@pytest.mark.parametrize(
    "url,payload,relative",
    [
        (
            "/plugin/writer/api/project/17/section/abstract/",
            {"content": "Edited synthetic alpha."},
            "01_manuscript/contents/abstract.tex",
        ),
        (
            "/plugin/writer/api/file?project=17",
            {"path": "00_shared/note.tex", "content": "Edited synthetic alpha."},
            "00_shared/note.tex",
        ),
    ],
)
def test_late_authorized_alpha_save_keeps_selected_beta(
    mounted, url, payload, relative
):
    client, roots = mounted
    csrf = choose_beta(client)
    denied = client.post(
        url,
        payload,
        content_type="application/json",
        HTTP_SELECTION_SESSION="synthetic",
    )
    assert denied.status_code == 403
    assert projects.selected == "21" and projects.remembered == []
    response = client.post(
        url,
        payload,
        content_type="application/json",
        HTTP_SELECTION_SESSION="synthetic",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200
    assert (roots["17"] / ".scitex/writer" / relative).read_text() == payload["content"]
    assert projects.selected == "21" and projects.remembered == []
    assert (
        roots["21"] / ".scitex/writer/01_manuscript/contents/abstract.tex"
    ).read_text() == "Synthetic beta abstract."


@pytest.mark.parametrize("page", ["", "viewer/"])
def test_explicit_editor_and_viewer_navigation_still_remembers(mounted, page):
    client, _ = mounted
    choose_beta(client)
    response = client.get(
        f"/plugin/writer/{page}?project=17", HTTP_SELECTION_SESSION="synthetic"
    )
    assert response.status_code == 200
    assert projects.selected == "17" and projects.remembered == ["17"]


def test_unselected_resource_reads_newer_beta_without_reselecting(mounted):
    client, roots = mounted
    choose_beta(client)
    response = client.get(
        "/plugin/writer/api/project-info", HTTP_SELECTION_SESSION="synthetic"
    )
    assert response.status_code == 200
    assert response.json()["project_dir"] == str(roots["21"] / ".scitex/writer")
    assert projects.selected == "21" and projects.remembered == []


def test_denied_and_conflicting_resource_selectors_keep_beta(mounted):
    client, _ = mounted
    choose_beta(client)
    for url, expected in [
        ("/plugin/writer/api/project/99/section/abstract/", 404),
        ("/plugin/writer/api/project/17/section/abstract/?project=21", 400),
    ]:
        response = client.get(url, HTTP_SELECTION_SESSION="synthetic")
        assert response.status_code == expected
        assert projects.selected == "21" and projects.remembered == []

"""Direct leaf mounts: real middleware, SDK providers and confined temp files.

No Hub wrapper, database, real account, compiler, network or fleet store.
"""

import re
from types import SimpleNamespace

import pytest
from django.test import Client, override_settings
from django.urls import include, path
from scitex_sdk.ui import project_scope

from scitex_writer._django import services, views


class SessionIdentity:
    """Test-only identity injection; creates no user rows or accounts."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = SimpleNamespace(is_authenticated=bool(request.headers.get("Audit-Session")))
        return self.get_response(request)


class Projects:
    selected = "owned"

    def list_projects(self, request):
        return [project_scope.ProjectEntry("owned", "Owned")]

    def last_visited(self, request):
        return self.selected

    def remember(self, request, project_id):
        self.selected = project_id


projects = Projects()


class Storage:
    def __init__(self, root, writable=True):
        self.root, self.writable = root, writable

    def project_path(self, project_id, request):
        return self.root if project_id == "owned" else None

    def can_write(self, project_id, request):
        return self.writable


urlpatterns = [
    path("host/writer/editor-alias/", views.editor_page,
         {"view_path": "editor-alias/", "api_base": "/host/writer/v2/"}, name="aliased-editor"),
    path("host/writer/viewer-alias/", views.viewer_page,
         {"view_path": "viewer-alias/", "api_base": "/host/writer/v2/"}, name="aliased-viewer"),
    path("plugin/writer/", include("scitex_writer._django.urls")),
]


def workspace(root):
    (root / "00_shared").mkdir(parents=True)
    (root / "01_manuscript/contents").mkdir(parents=True)
    (root / "01_manuscript/contents/text.tex").write_text("Synthetic prose")
    return root


@pytest.fixture
def mounted(tmp_path):
    root = tmp_path / "owned"
    candidate = workspace(root / ".scitex/writer")
    foreign = workspace(tmp_path / "foreign")
    services._project_cache.clear()
    projects.selected = "owned"
    storage = Storage(root)
    with override_settings(
        SCITEX_APP_MODE="hub", ROOT_URLCONF=__name__, ALLOWED_HOSTS=["testserver"],
        MIDDLEWARE=[__name__ + ".SessionIdentity"], LOGIN_URL="/login/",
        SCITEX_PROJECT_PROVIDER=__name__ + ".projects", SCITEX_PROJECT_STORAGE=storage,
    ):
        yield Client(enforce_csrf_checks=True), storage, candidate, foreign
    services._project_cache.clear()


def token(client):
    response = client.get("/plugin/writer/", HTTP_AUDIT_SESSION="synthetic")
    assert response.status_code == 200
    return client.cookies["csrftoken"].value


@pytest.mark.parametrize("route", ["", "viewer/", "ping", "api/project-info", "api/file", "api/compile"])
def test_anonymous_requests_never_reach_project_or_handlers(mounted, route):
    client, _, candidate, _ = mounted
    response = client.get("/plugin/writer/" + route)
    assert response.status_code == (302 if route in {"", "viewer/"} else 401)
    assert not services._project_cache
    assert not (candidate / "00_shared/scholar").exists()


def test_plugin_ignores_duplicate_caller_and_environment_working_dirs(mounted, monkeypatch):
    client, _, candidate, foreign = mounted
    monkeypatch.setenv("SCITEX_WRITER_WORKING_DIR", str(foreign))
    response = client.get(
        "/plugin/writer/api/project-info",
        {"working_dir": [str(foreign), str(foreign.parent)], "project": "owned"},
        HTTP_AUDIT_SESSION="synthetic",
    )
    assert response.status_code == 200
    assert response.json()["project_dir"] == str(candidate)
    assert not (candidate / "00_shared/scholar").exists()
    assert not (foreign / "00_shared/scholar").exists()


def test_denied_explicit_project_does_not_fall_back(mounted):
    client, _, _, _ = mounted
    response = client.get("/plugin/writer/ping?project=foreign", HTTP_AUDIT_SESSION="synthetic")
    assert response.status_code == 404
    assert projects.selected == "owned"
    assert not services._project_cache


@pytest.mark.parametrize("missing", ["SCITEX_PROJECT_PROVIDER", "SCITEX_PROJECT_STORAGE"])
def test_missing_capability_does_not_use_local_defaults(mounted, missing):
    client, _, _, foreign = mounted
    with override_settings(**{missing: ""}):
        response = client.get("/plugin/writer/ping", {"working_dir": str(foreign)}, HTTP_AUDIT_SESSION="synthetic")
    assert response.status_code == 503
    assert not services._project_cache


@pytest.mark.parametrize("writable", [False, None, 0, 1, "true", "false"])
def test_write_permission_requires_literal_true_before_loading_state(mounted, writable):
    client, storage, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    storage.writable = writable
    response = client.post("/plugin/writer/api/file", {"path": "new.tex", "content": "X"},
                           content_type="application/json", HTTP_AUDIT_SESSION="synthetic", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 403
    assert not (candidate / "new.tex").exists()
    assert not services._project_cache


@pytest.mark.parametrize("mode", ["invalid", "Standalone", None, {}, []])
def test_invalid_mode_denies_anonymous_and_authenticated_requests(mounted, mode):
    client, _, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    projects.selected = None
    with override_settings(SCITEX_APP_MODE=mode):
        for identity in ["", "synthetic"]:
            for route in ["", "api/project-info"]:
                response = client.get("/plugin/writer/" + route, HTTP_AUDIT_SESSION=identity)
                assert response.status_code == 503
            response = client.post("/plugin/writer/api/file?project=owned",
                                   {"path": "new.tex", "content": "X"},
                                   content_type="application/json", HTTP_AUDIT_SESSION=identity,
                                   HTTP_X_CSRFTOKEN=csrf)
            assert response.status_code == 503
    assert projects.selected is None
    assert not services._project_cache
    assert not (candidate / "new.tex").exists()


def test_session_csrf_denial_and_authorized_save_ignore_body_working_dir(mounted):
    client, _, candidate, foreign = mounted
    csrf = token(client)
    data = {"path": "01_manuscript/contents/text.tex", "content": "Edited synthetic prose", "working_dir": str(foreign)}
    url = "/plugin/writer/api/file?working_dir=" + str(foreign)
    denied = client.post(url, data, content_type="application/json", HTTP_AUDIT_SESSION="synthetic")
    assert denied.status_code == 403
    assert (candidate / data["path"]).read_text() == "Synthetic prose"
    allowed = client.post(url, data, content_type="application/json", HTTP_AUDIT_SESSION="synthetic", HTTP_X_CSRFTOKEN=csrf)
    assert allowed.status_code == 200
    assert (candidate / data["path"]).read_text() == data["content"]
    assert (foreign / data["path"]).read_text() == "Synthetic prose"


def test_csrf_rejection_cannot_change_active_project(mounted):
    client, _, _, _ = mounted
    token(client)
    projects.selected = None
    response = client.post("/plugin/writer/api/file?project=owned", {"path": "new.tex", "content": "X"},
                           content_type="application/json", HTTP_AUDIT_SESSION="synthetic")
    assert response.status_code == 403
    assert projects.selected is None


def test_cross_origin_write_with_token_is_denied(mounted):
    client, _, candidate, _ = mounted
    response = client.post("/plugin/writer/api/file", {"path": "new.tex", "content": "X"},
                           content_type="application/json", HTTP_AUDIT_SESSION="synthetic",
                           HTTP_X_CSRFTOKEN=token(client), HTTP_ORIGIN="https://attacker.invalid")
    assert response.status_code == 403
    assert not (candidate / "new.tex").exists()


def test_workspace_symlink_cannot_escape_authorized_project(mounted):
    client, storage, _, foreign = mounted
    other = storage.root.parent / "other"
    (other / ".scitex").mkdir(parents=True)
    (other / ".scitex/writer").symlink_to(foreign, target_is_directory=True)
    storage.root = other
    response = client.get("/plugin/writer/ping", HTTP_AUDIT_SESSION="synthetic")
    assert response.status_code == 403
    assert not services._project_cache


def test_file_tree_and_reads_confine_symlinks_and_traversal(mounted):
    client, _, candidate, foreign = mounted
    (candidate / "outbound").symlink_to(foreign, target_is_directory=True)
    (candidate / "cycle").symlink_to(candidate, target_is_directory=True)
    listing = client.get("/plugin/writer/api/files", HTTP_AUDIT_SESSION="synthetic")
    assert listing.status_code == 200
    assert "outbound" not in {item["name"] for item in listing.json()["tree"]}
    for relative in ["outbound/01_manuscript/contents/text.tex", "../../foreign/01_manuscript/contents/text.tex", str(foreign / "01_manuscript/contents/text.tex")]:
        denied = client.get("/plugin/writer/api/file", {"path": relative}, HTTP_AUDIT_SESSION="synthetic")
        assert denied.status_code == 403


def test_standard_plugin_mount_supplies_own_api_base_and_csrf(mounted):
    client, _, _, _ = mounted
    for route in ["", "viewer/"]:
        response = client.get("/plugin/writer/" + route, HTTP_AUDIT_SESSION="synthetic")
        assert response.status_code == 200
        body = response.content.decode()
        assert 'data-api-base="/plugin/writer/"' in body
        assert 'data-app-mode="hub"' in body
        assert 'name="writer-csrf-token"' in body
        assert 'name="stx-app-scope" content="project"' in body


def test_trusted_host_aliases_can_declare_mount_without_query_override(mounted):
    client, _, _, _ = mounted
    for route in ["editor-alias", "viewer-alias"]:
        response = client.get("/host/writer/" + route + "/?api_base=https://attacker.invalid/",
                              HTTP_AUDIT_SESSION="synthetic")
        assert response.status_code == 200
        body = response.content.decode()
        assert 'data-api-base="/host/writer/v2/"' in body
        assert 'name="stx-mount" content="/host/writer"' in body
        assert "https://attacker.invalid/" not in body


def test_standalone_local_file_save_requires_session_csrf(mounted):
    _, _, _, local = mounted
    with override_settings(SCITEX_APP_MODE="standalone", ROOT_URLCONF="scitex_writer._django._standalone_urls", MIDDLEWARE=[]):
        client = Client(enforce_csrf_checks=True)
        assert client.get("/", {"working_dir": str(local)}).status_code == 200
        payload = {"path": "new.tex", "content": "Local synthetic input"}
        url = "/api/file?working_dir=" + str(local)
        assert client.post(url, payload, content_type="application/json").status_code == 403
        assert client.post(url, payload, content_type="application/json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value).status_code == 200
        assert (local / "new.tex").read_text() == payload["content"]


@pytest.mark.parametrize("session_token", [False, True])
def test_rendered_token_works_with_http_only_cookie_and_session_storage(mounted, session_token):
    _, _, _, local = mounted
    with override_settings(SCITEX_APP_MODE="standalone", ROOT_URLCONF="scitex_writer._django._standalone_urls",
                           MIDDLEWARE=["django.contrib.sessions.middleware.SessionMiddleware"],
                           SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
                           CSRF_COOKIE_HTTPONLY=True, CSRF_USE_SESSIONS=session_token):
        client = Client(enforce_csrf_checks=True)
        response = client.get("/", {"working_dir": str(local)})
        csrf = re.search(r'name="writer-csrf-token" content="([^"]+)"', response.content.decode()).group(1)
        saved = client.post("/api/file?working_dir=" + str(local), {"path": "new.tex", "content": "X"},
                            content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        assert saved.status_code == 200
        assert (local / "new.tex").read_text() == "X"

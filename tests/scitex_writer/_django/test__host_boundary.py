"""Direct leaf mounts: real middleware, SDK providers and confined temp files.

No Hub wrapper, database, real account, compiler, network or fleet store.
"""

import os
import re
from contextlib import contextmanager
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
    path("relocated/writer/", include("scitex_writer._django.urls")),
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


@pytest.mark.parametrize('route', ['', 'viewer/', 'ping', 'api/project-info', 'api/file', 'api/compile', 'editor-v2/', 'viewer-v2/', 'v2/ping', 'v2/api/project-info'])
def test_anonymous_requests_never_reach_project_or_handlers_returns_authentication_refusal(mounted, route):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    # Act: exercise the real scenario.
    response = client.get('/plugin/writer/' + route)
    # Assert
    assert response.status_code == (302 if route in {'', 'viewer/', 'editor-v2/', 'viewer-v2/'} else 401)


@pytest.mark.parametrize('route', ['', 'viewer/', 'ping', 'api/project-info', 'api/file', 'api/compile', 'editor-v2/', 'viewer-v2/', 'v2/ping', 'v2/api/project-info'])
def test_anonymous_requests_never_reach_project_or_handlers_leaves_project_cache_empty(mounted, route):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    # Act: exercise the real scenario.
    response = client.get('/plugin/writer/' + route)
    # Assert
    assert not services._project_cache


@pytest.mark.parametrize('route', ['', 'viewer/', 'ping', 'api/project-info', 'api/file', 'api/compile'])
def test_anonymous_requests_never_reach_project_or_handlers_does_not_create_scholar(mounted, route):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    # Act: exercise the real scenario.
    response = client.get('/plugin/writer/' + route)
    # Assert
    assert not (candidate / '00_shared/scholar').exists()


@contextmanager
def environment_value(key, value):
    """Exercise the real environment and restore its exact previous value."""
    previous = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def test_plugin_ignores_duplicate_caller_and_environment_working_dirs_returns_success(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    with environment_value('SCITEX_WRITER_WORKING_DIR', str(foreign)):
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/api/project-info', {'working_dir': [str(foreign), str(foreign.parent)], 'project': 'owned'}, HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert response.status_code == 200


def test_plugin_ignores_duplicate_caller_and_environment_working_dirs_uses_authorized_project_root(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    with environment_value('SCITEX_WRITER_WORKING_DIR', str(foreign)):
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/api/project-info', {'working_dir': [str(foreign), str(foreign.parent)], 'project': 'owned'}, HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert response.json()['project_dir'] == str(candidate)


def test_plugin_ignores_duplicate_caller_and_environment_working_dirs_does_not_create_owned_scholar(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    with environment_value('SCITEX_WRITER_WORKING_DIR', str(foreign)):
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/api/project-info', {'working_dir': [str(foreign), str(foreign.parent)], 'project': 'owned'}, HTTP_AUDIT_SESSION='synthetic')
    response.json()
    str(candidate)
    # Assert
    assert not (candidate / '00_shared/scholar').exists()


def test_plugin_ignores_duplicate_caller_and_environment_working_dirs_does_not_create_foreign_scholar(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    with environment_value('SCITEX_WRITER_WORKING_DIR', str(foreign)):
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/api/project-info', {'working_dir': [str(foreign), str(foreign.parent)], 'project': 'owned'}, HTTP_AUDIT_SESSION='synthetic')
    response.json()
    str(candidate)
    (candidate / '00_shared/scholar').exists()
    # Assert
    assert not (foreign / '00_shared/scholar').exists()


def test_denied_explicit_project_does_not_fall_back_returns_not_found(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    # Act: exercise the real scenario.
    response = client.get('/plugin/writer/ping?project=foreign', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert response.status_code == 404


def test_denied_explicit_project_does_not_fall_back_preserves_selected_project(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    # Act: exercise the real scenario.
    response = client.get('/plugin/writer/ping?project=foreign', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert projects.selected == 'owned'


def test_denied_explicit_project_does_not_fall_back_leaves_project_cache_empty(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    # Act: exercise the real scenario.
    response = client.get('/plugin/writer/ping?project=foreign', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert not services._project_cache


@pytest.mark.parametrize('missing', ['SCITEX_PROJECT_PROVIDER', 'SCITEX_PROJECT_STORAGE'])
@pytest.mark.parametrize('route', ['ping', 'v2/ping'])
def test_missing_capability_does_not_use_local_defaults_returns_unavailable(mounted, missing, route):
    # Arrange: pytest fixtures and local setup.
    client, _, _, foreign = mounted
    with override_settings(**{missing: ''}):
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/' + route, {'working_dir': str(foreign)}, HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert response.status_code == 503


@pytest.mark.parametrize('missing', ['SCITEX_PROJECT_PROVIDER', 'SCITEX_PROJECT_STORAGE'])
def test_missing_capability_does_not_use_local_defaults_leaves_project_cache_empty(mounted, missing):
    # Arrange: pytest fixtures and local setup.
    client, _, _, foreign = mounted
    with override_settings(**{missing: ''}):
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/ping', {'working_dir': str(foreign)}, HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert not services._project_cache


@pytest.mark.parametrize('writable', [False, None, 0, 1, 'true', 'false'])
def test_write_permission_requires_literal_true_before_loading_state_returns_forbidden(mounted, writable):
    # Arrange: pytest fixtures and local setup.
    client, storage, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    storage.writable = writable
    # Act: exercise the real scenario.
    response = client.post('/plugin/writer/api/file', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION='synthetic', HTTP_X_CSRFTOKEN=csrf)
    # Assert
    assert response.status_code == 403


@pytest.mark.parametrize('writable', [False, None, 0, 1, 'true', 'false'])
def test_write_permission_requires_literal_true_before_loading_state_does_not_create_file(mounted, writable):
    # Arrange: pytest fixtures and local setup.
    client, storage, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    storage.writable = writable
    # Act: exercise the real scenario.
    response = client.post('/plugin/writer/api/file', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION='synthetic', HTTP_X_CSRFTOKEN=csrf)
    # Assert
    assert not (candidate / 'new.tex').exists()


@pytest.mark.parametrize('writable', [False, None, 0, 1, 'true', 'false'])
def test_write_permission_requires_literal_true_before_loading_state_leaves_project_cache_empty(mounted, writable):
    # Arrange: pytest fixtures and local setup.
    client, storage, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    storage.writable = writable
    # Act: exercise the real scenario.
    response = client.post('/plugin/writer/api/file', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION='synthetic', HTTP_X_CSRFTOKEN=csrf)
    (candidate / 'new.tex').exists()
    # Assert
    assert not services._project_cache


@pytest.mark.parametrize('mode', ['invalid', 'Standalone', None, {}, []])
def test_invalid_mode_denies_anonymous_and_authenticated_requests_refuses_read_requests(mounted, mode):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    projects.selected = None
    with override_settings(SCITEX_APP_MODE=mode):
        for identity in ['', 'synthetic']:
            for route in ['', 'api/project-info']:
                # Act: exercise the real scenario.
                response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION=identity)
                # Assert
                assert response.status_code == 503


@pytest.mark.parametrize('mode', ['invalid', 'Standalone', None, {}, []])
def test_invalid_mode_denies_anonymous_and_authenticated_requests_refuses_write_requests(mounted, mode):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    projects.selected = None
    with override_settings(SCITEX_APP_MODE=mode):
        for identity in ['', 'synthetic']:
            for route in ['', 'api/project-info']:
                # Act: exercise the real scenario.
                response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION=identity)
            response = client.post('/plugin/writer/api/file?project=owned', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION=identity, HTTP_X_CSRFTOKEN=csrf)
            # Assert
            assert response.status_code == 503


@pytest.mark.parametrize('mode', ['invalid', 'Standalone', None, {}, []])
def test_invalid_mode_denies_anonymous_and_authenticated_requests_preserves_unselected_project(mounted, mode):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    projects.selected = None
    with override_settings(SCITEX_APP_MODE=mode):
        for identity in ['', 'synthetic']:
            for route in ['', 'api/project-info']:
                # Act: exercise the real scenario.
                response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION=identity)
            response = client.post('/plugin/writer/api/file?project=owned', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION=identity, HTTP_X_CSRFTOKEN=csrf)
    # Assert
    assert projects.selected is None


@pytest.mark.parametrize('mode', ['invalid', 'Standalone', None, {}, []])
def test_invalid_mode_denies_anonymous_and_authenticated_requests_leaves_project_cache_empty(mounted, mode):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    projects.selected = None
    with override_settings(SCITEX_APP_MODE=mode):
        for identity in ['', 'synthetic']:
            for route in ['', 'api/project-info']:
                # Act: exercise the real scenario.
                response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION=identity)
            response = client.post('/plugin/writer/api/file?project=owned', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION=identity, HTTP_X_CSRFTOKEN=csrf)
    # Assert
    assert not services._project_cache


@pytest.mark.parametrize('mode', ['invalid', 'Standalone', None, {}, []])
def test_invalid_mode_denies_anonymous_and_authenticated_requests_does_not_create_file(mounted, mode):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    csrf = token(client)
    services._project_cache.clear()
    projects.selected = None
    with override_settings(SCITEX_APP_MODE=mode):
        for identity in ['', 'synthetic']:
            for route in ['', 'api/project-info']:
                # Act: exercise the real scenario.
                response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION=identity)
            response = client.post('/plugin/writer/api/file?project=owned', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION=identity, HTTP_X_CSRFTOKEN=csrf)
    # Assert
    assert not (candidate / 'new.tex').exists()


@pytest.mark.parametrize('route', ['api/file', 'v2/api/file'])
def test_session_csrf_denial_and_authorized_save_ignore_body_working_dir_denies_missing_csrf(mounted, route):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    csrf = token(client)
    data = {'path': '01_manuscript/contents/text.tex', 'content': 'Edited synthetic prose', 'working_dir': str(foreign)}
    url = '/plugin/writer/' + route + '?working_dir=' + str(foreign)
    # Act: exercise the real scenario.
    denied = client.post(url, data, content_type='application/json', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert denied.status_code == 403


def test_session_csrf_denial_and_authorized_save_ignore_body_working_dir_denied_save_preserves_content(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    csrf = token(client)
    data = {'path': '01_manuscript/contents/text.tex', 'content': 'Edited synthetic prose', 'working_dir': str(foreign)}
    url = '/plugin/writer/api/file?working_dir=' + str(foreign)
    # Act: exercise the real scenario.
    denied = client.post(url, data, content_type='application/json', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert (candidate / data['path']).read_text() == 'Synthetic prose'


def test_session_csrf_denial_and_authorized_save_ignore_body_working_dir_accepts_valid_csrf(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    csrf = token(client)
    data = {'path': '01_manuscript/contents/text.tex', 'content': 'Edited synthetic prose', 'working_dir': str(foreign)}
    url = '/plugin/writer/api/file?working_dir=' + str(foreign)
    # Act: exercise the real scenario.
    denied = client.post(url, data, content_type='application/json', HTTP_AUDIT_SESSION='synthetic')
    (candidate / data['path']).read_text()
    allowed = client.post(url, data, content_type='application/json', HTTP_AUDIT_SESSION='synthetic', HTTP_X_CSRFTOKEN=csrf)
    # Assert
    assert allowed.status_code == 200


@pytest.mark.parametrize('route', ['api/file', 'v2/api/file'])
def test_session_csrf_denial_and_authorized_save_ignore_body_working_dir_writes_owned_file(mounted, route):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    csrf = token(client)
    data = {'path': '01_manuscript/contents/text.tex', 'content': 'Edited synthetic prose', 'working_dir': str(foreign)}
    url = '/plugin/writer/' + route + '?working_dir=' + str(foreign)
    # Act: exercise the real scenario.
    denied = client.post(url, data, content_type='application/json', HTTP_AUDIT_SESSION='synthetic')
    (candidate / data['path']).read_text()
    allowed = client.post(url, data, content_type='application/json', HTTP_AUDIT_SESSION='synthetic', HTTP_X_CSRFTOKEN=csrf)
    # Assert
    assert (candidate / data['path']).read_text() == data['content']


def test_session_csrf_denial_and_authorized_save_ignore_body_working_dir_preserves_foreign_file(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    csrf = token(client)
    data = {'path': '01_manuscript/contents/text.tex', 'content': 'Edited synthetic prose', 'working_dir': str(foreign)}
    url = '/plugin/writer/api/file?working_dir=' + str(foreign)
    # Act: exercise the real scenario.
    denied = client.post(url, data, content_type='application/json', HTTP_AUDIT_SESSION='synthetic')
    (candidate / data['path']).read_text()
    allowed = client.post(url, data, content_type='application/json', HTTP_AUDIT_SESSION='synthetic', HTTP_X_CSRFTOKEN=csrf)
    (candidate / data['path']).read_text()
    # Assert
    assert (foreign / data['path']).read_text() == 'Synthetic prose'


def test_csrf_rejection_cannot_change_active_project_returns_forbidden(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    token(client)
    projects.selected = None
    # Act: exercise the real scenario.
    response = client.post('/plugin/writer/api/file?project=owned', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert response.status_code == 403


def test_csrf_rejection_cannot_change_active_project_preserves_unselected_project(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    token(client)
    projects.selected = None
    # Act: exercise the real scenario.
    response = client.post('/plugin/writer/api/file?project=owned', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert projects.selected is None


def test_cross_origin_write_with_token_is_denied_returns_forbidden(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    # Act: exercise the real scenario.
    response = client.post('/plugin/writer/api/file', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION='synthetic', HTTP_X_CSRFTOKEN=token(client), HTTP_ORIGIN='https://attacker.invalid')
    # Assert
    assert response.status_code == 403


def test_cross_origin_write_with_token_is_denied_does_not_create_file(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, _ = mounted
    # Act: exercise the real scenario.
    response = client.post('/plugin/writer/api/file', {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_AUDIT_SESSION='synthetic', HTTP_X_CSRFTOKEN=token(client), HTTP_ORIGIN='https://attacker.invalid')
    # Assert
    assert not (candidate / 'new.tex').exists()


@pytest.mark.parametrize('route', ['ping', 'v2/ping'])
def test_workspace_symlink_cannot_escape_authorized_project_returns_forbidden(mounted, route):
    # Arrange: pytest fixtures and local setup.
    client, storage, _, foreign = mounted
    other = storage.root.parent / 'other'
    (other / '.scitex').mkdir(parents=True)
    (other / '.scitex/writer').symlink_to(foreign, target_is_directory=True)
    storage.root = other
    # Act: exercise the real scenario.
    response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert response.status_code == 403


def test_workspace_symlink_cannot_escape_authorized_project_leaves_project_cache_empty(mounted):
    # Arrange: pytest fixtures and local setup.
    client, storage, _, foreign = mounted
    other = storage.root.parent / 'other'
    (other / '.scitex').mkdir(parents=True)
    (other / '.scitex/writer').symlink_to(foreign, target_is_directory=True)
    storage.root = other
    # Act: exercise the real scenario.
    response = client.get('/plugin/writer/ping', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert not services._project_cache


def test_file_tree_and_reads_confine_symlinks_and_traversal_returns_tree_success(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    (candidate / 'outbound').symlink_to(foreign, target_is_directory=True)
    (candidate / 'cycle').symlink_to(candidate, target_is_directory=True)
    # Act: exercise the real scenario.
    listing = client.get('/plugin/writer/api/files', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert listing.status_code == 200


def test_file_tree_and_reads_confine_symlinks_and_traversal_omits_outbound_symlink(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    (candidate / 'outbound').symlink_to(foreign, target_is_directory=True)
    (candidate / 'cycle').symlink_to(candidate, target_is_directory=True)
    # Act: exercise the real scenario.
    listing = client.get('/plugin/writer/api/files', HTTP_AUDIT_SESSION='synthetic')
    # Assert
    assert 'outbound' not in {item['name'] for item in listing.json()['tree']}


def test_file_tree_and_reads_confine_symlinks_and_traversal_refuses_escaped_paths(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, candidate, foreign = mounted
    (candidate / 'outbound').symlink_to(foreign, target_is_directory=True)
    (candidate / 'cycle').symlink_to(candidate, target_is_directory=True)
    # Act: exercise the real scenario.
    listing = client.get('/plugin/writer/api/files', HTTP_AUDIT_SESSION='synthetic')
    listing.json()
    for relative in ['outbound/01_manuscript/contents/text.tex', '../../foreign/01_manuscript/contents/text.tex', str(foreign / '01_manuscript/contents/text.tex')]:
        denied = client.get('/plugin/writer/api/file', {'path': relative}, HTTP_AUDIT_SESSION='synthetic')
        # Assert
        assert denied.status_code == 403


def test_standard_plugin_mount_supplies_own_api_base_and_csrf_returns_page_success(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    for route in ['', 'viewer/']:
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION='synthetic')
        # Assert
        assert response.status_code == 200


def test_standard_plugin_mount_supplies_own_api_base_and_csrf_declares_plugin_api_base(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    for route in ['', 'viewer/']:
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION='synthetic')
        body = response.content.decode()
        # Assert
        assert 'data-api-base="/plugin/writer/"' in body


def test_standard_plugin_mount_supplies_own_api_base_and_csrf_declares_hub_mode(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    for route in ['', 'viewer/']:
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION='synthetic')
        body = response.content.decode()
        # Assert
        assert 'data-app-mode="hub"' in body


def test_standard_plugin_mount_supplies_own_api_base_and_csrf_renders_csrf_token(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    for route in ['', 'viewer/']:
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION='synthetic')
        body = response.content.decode()
        # Assert
        assert 'name="writer-csrf-token"' in body


def test_standard_plugin_mount_supplies_own_api_base_and_csrf_declares_project_scope(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    for route in ['', 'viewer/']:
        # Act: exercise the real scenario.
        response = client.get('/plugin/writer/' + route, HTTP_AUDIT_SESSION='synthetic')
        body = response.content.decode()
        # Assert
        assert 'name="stx-app-scope" content="project"' in body


def test_trusted_host_aliases_can_declare_mount_without_query_override_returns_page_success(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    for route in ['editor-alias', 'viewer-alias']:
        # Act: exercise the real scenario.
        response = client.get('/host/writer/' + route + '/?api_base=https://attacker.invalid/', HTTP_AUDIT_SESSION='synthetic')
        # Assert
        assert response.status_code == 200


def test_trusted_host_aliases_can_declare_mount_without_query_override_declares_host_api_base(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    for route in ['editor-alias', 'viewer-alias']:
        # Act: exercise the real scenario.
        response = client.get('/host/writer/' + route + '/?api_base=https://attacker.invalid/', HTTP_AUDIT_SESSION='synthetic')
        body = response.content.decode()
        # Assert
        assert 'data-api-base="/host/writer/v2/"' in body


def test_trusted_host_aliases_can_declare_mount_without_query_override_declares_host_mount(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    for route in ['editor-alias', 'viewer-alias']:
        # Act: exercise the real scenario.
        response = client.get('/host/writer/' + route + '/?api_base=https://attacker.invalid/', HTTP_AUDIT_SESSION='synthetic')
        body = response.content.decode()
        # Assert
        assert 'name="stx-mount" content="/host/writer"' in body


def test_trusted_host_aliases_can_declare_mount_without_query_override_refuses_query_api_base(mounted):
    # Arrange: pytest fixtures and local setup.
    client, _, _, _ = mounted
    for route in ['editor-alias', 'viewer-alias']:
        # Act: exercise the real scenario.
        response = client.get('/host/writer/' + route + '/?api_base=https://attacker.invalid/', HTTP_AUDIT_SESSION='synthetic')
        body = response.content.decode()
        # Assert
        assert 'https://attacker.invalid/' not in body


def test_standalone_local_file_save_requires_session_csrf_returns_page_success(mounted):
    # Arrange: pytest fixtures and local setup.
    _, _, _, local = mounted
    with override_settings(SCITEX_APP_MODE='standalone', ROOT_URLCONF='scitex_writer._django._standalone_urls', MIDDLEWARE=[]):
        client = Client(enforce_csrf_checks=True)
        # Act: exercise the real scenario.
        # Assert
        assert client.get('/', {'working_dir': str(local)}).status_code == 200


def test_standalone_local_file_save_requires_session_csrf_denies_missing_csrf(mounted):
    # Arrange: pytest fixtures and local setup.
    _, _, _, local = mounted
    with override_settings(SCITEX_APP_MODE='standalone', ROOT_URLCONF='scitex_writer._django._standalone_urls', MIDDLEWARE=[]):
        client = Client(enforce_csrf_checks=True)
        # Act: exercise the real scenario.
        client.get('/', {'working_dir': str(local)})
        payload = {'path': 'new.tex', 'content': 'Local synthetic input'}
        url = '/api/file?working_dir=' + str(local)
        # Assert
        assert client.post(url, payload, content_type='application/json').status_code == 403


def test_standalone_local_file_save_requires_session_csrf_accepts_valid_csrf(mounted):
    # Arrange: pytest fixtures and local setup.
    _, _, _, local = mounted
    with override_settings(SCITEX_APP_MODE='standalone', ROOT_URLCONF='scitex_writer._django._standalone_urls', MIDDLEWARE=[]):
        client = Client(enforce_csrf_checks=True)
        # Act: exercise the real scenario.
        client.get('/', {'working_dir': str(local)})
        payload = {'path': 'new.tex', 'content': 'Local synthetic input'}
        url = '/api/file?working_dir=' + str(local)
        client.post(url, payload, content_type='application/json')
        # Assert
        assert client.post(url, payload, content_type='application/json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value).status_code == 200


def test_standalone_local_file_save_requires_session_csrf_writes_authorized_file(mounted):
    # Arrange: pytest fixtures and local setup.
    _, _, _, local = mounted
    with override_settings(SCITEX_APP_MODE='standalone', ROOT_URLCONF='scitex_writer._django._standalone_urls', MIDDLEWARE=[]):
        client = Client(enforce_csrf_checks=True)
        # Act: exercise the real scenario.
        client.get('/', {'working_dir': str(local)})
        payload = {'path': 'new.tex', 'content': 'Local synthetic input'}
        url = '/api/file?working_dir=' + str(local)
        client.post(url, payload, content_type='application/json')
        client.post(url, payload, content_type='application/json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        # Assert
        assert (local / 'new.tex').read_text() == payload['content']


@pytest.mark.parametrize('session_token', [False, True])
def test_rendered_token_works_with_http_only_cookie_and_session_storage_accepts_rendered_csrf_token(mounted, session_token):
    # Arrange: pytest fixtures and local setup.
    _, _, _, local = mounted
    with override_settings(SCITEX_APP_MODE='standalone', ROOT_URLCONF='scitex_writer._django._standalone_urls', MIDDLEWARE=['django.contrib.sessions.middleware.SessionMiddleware'], SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies', CSRF_COOKIE_HTTPONLY=True, CSRF_USE_SESSIONS=session_token):
        client = Client(enforce_csrf_checks=True)
        # Act: exercise the real scenario.
        response = client.get('/', {'working_dir': str(local)})
        csrf = re.search('name="writer-csrf-token" content="([^"]+)"', response.content.decode()).group(1)
        saved = client.post('/api/file?working_dir=' + str(local), {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
        # Assert
        assert saved.status_code == 200


@pytest.mark.parametrize('session_token', [False, True])
def test_rendered_token_works_with_http_only_cookie_and_session_storage_writes_authorized_file(mounted, session_token):
    # Arrange: pytest fixtures and local setup.
    _, _, _, local = mounted
    with override_settings(SCITEX_APP_MODE='standalone', ROOT_URLCONF='scitex_writer._django._standalone_urls', MIDDLEWARE=['django.contrib.sessions.middleware.SessionMiddleware'], SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies', CSRF_COOKIE_HTTPONLY=True, CSRF_USE_SESSIONS=session_token):
        client = Client(enforce_csrf_checks=True)
        # Act: exercise the real scenario.
        response = client.get('/', {'working_dir': str(local)})
        csrf = re.search('name="writer-csrf-token" content="([^"]+)"', response.content.decode()).group(1)
        saved = client.post('/api/file?working_dir=' + str(local), {'path': 'new.tex', 'content': 'X'}, content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
        # Assert
        assert (local / 'new.tex').read_text() == 'X'


@pytest.mark.parametrize('prefix', ['/plugin/writer/', '/relocated/writer/'])
@pytest.mark.parametrize('route', ['editor-v2/', 'viewer-v2/'])
def test_v2_pages_derive_api_base_from_actual_include(mounted, prefix, route):
    # Arrange
    client, _, _, _ = mounted
    # Act
    response = client.get(
        prefix + route,
        {'api_base': 'https://attacker.invalid/', 'view_path': '/spoofed/'},
        HTTP_AUDIT_SESSION='synthetic',
    )
    body = response.content.decode()
    # Assert
    assert re.search(r'data-api-base="([^"]+)"', body).group(1) == prefix + 'v2/'


@pytest.mark.parametrize('prefix', ['/plugin/writer/', '/relocated/writer/'])
@pytest.mark.parametrize('route', ['editor-v2/', 'viewer-v2/'])
def test_v2_pages_declare_actual_mount_without_route_suffix(mounted, prefix, route):
    # Arrange
    client, _, _, _ = mounted
    # Act
    response = client.get(prefix + route, HTTP_AUDIT_SESSION='synthetic')
    body = response.content.decode()
    # Assert
    assert re.search(r'name="stx-mount" content="([^"]*)"', body).group(1) == prefix.rstrip('/')


@pytest.mark.parametrize('prefix', ['/plugin/writer/', '/relocated/writer/'])
@pytest.mark.parametrize('route', ['editor-v2/', 'viewer-v2/'])
def test_v2_rendered_csrf_token_authorizes_confined_save(mounted, prefix, route):
    # Arrange
    client, _, candidate, foreign = mounted
    # Act
    response = client.get(prefix + route, HTTP_AUDIT_SESSION='synthetic')
    csrf = re.search(r'name="writer-csrf-token" content="([^"]+)"', response.content.decode()).group(1)
    client.post(
        prefix + 'v2/api/file',
        {'path': 'new-v2.tex', 'content': 'V2 synthetic prose', 'working_dir': str(foreign)},
        content_type='application/json', HTTP_AUDIT_SESSION='synthetic',
        HTTP_X_CSRFTOKEN=csrf,
    )
    # Assert
    assert (candidate / 'new-v2.tex').read_text() == 'V2 synthetic prose'

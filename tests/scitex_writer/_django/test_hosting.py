"""Real leaf fragments, SDK capabilities and confined files; no Hub runtime."""

import re
import sys
from html.parser import HTMLParser
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
from django.http import HttpResponse
from django.template.loader import get_template, render_to_string
from django.test import Client, RequestFactory, override_settings
from django.urls import (
    clear_url_caches,
    get_script_prefix,
    get_urlconf,
    include,
    path,
    set_script_prefix,
    set_urlconf,
)
from django.utils.module_loading import import_string
from scitex_sdk import host
from scitex_sdk.app.plugins import leaf_declarations
from scitex_sdk.app.project_context import ActiveProject

from scitex_writer._django import hosting, services

from .test__host_boundary import SessionIdentity, workspace
from .test_views_project_selection import Projects


class ObservedProjects(Projects):
    """Observe the existing real provider protocol without replacing the SDK."""

    def __init__(self):
        super().__init__()
        self.selected = "21"
        self.lookups = []

    def list_projects(self, request):
        self.lookups.append("list")
        return super().list_projects(request)

    def last_visited(self, request):
        self.lookups.append("last")
        return super().last_visited(request)


class Storage:
    def __init__(self, roots):
        self.roots = roots
        self.writable = True
        self.path_calls = []

    def project_path(self, project_id, request):
        self.path_calls.append(project_id)
        return self.roots.get(project_id)

    def can_write(self, project_id, request):
        return self.writable


class DocumentShellTokens(HTMLParser):
    """Observe document tokens while HTMLParser excludes comments and raw text."""

    def __init__(self):
        super().__init__()
        self.tokens = set()

    def handle_starttag(self, tag, attrs):
        if tag in {"html", "head", "body"}:
            self.tokens.add(tag)

    def handle_endtag(self, tag):
        if tag in {"html", "head", "body"}:
            self.tokens.add(tag)

    def handle_decl(self, decl):
        words = decl.split(maxsplit=1)
        if words and words[0].lower() == "doctype":
            self.tokens.add("doctype")


def document_shell_tokens(html):
    parser = DocumentShellTokens()
    parser.feed(html)
    parser.close()
    return parser.tokens


def urlconf_for(prefix, *, content_mount=None):
    """A real include and a generic content URL with trusted server defaults."""
    module = ModuleType("writer_hosting_" + prefix.replace("/", "_"))
    module.urlpatterns = [
        path(prefix.strip("/") + "/", include("scitex_writer._django.urls")),
        path(
            "workspace/content/",
            hosting.render_content,
            {
                "current_project": ActiveProject("17", "Alpha"),
                "stx_mount": prefix + "/" if content_mount is None else content_mount,
            },
        ),
    ]
    return module


@pytest.fixture
def mounted(tmp_path, request):
    prefix = getattr(request, "param", "/plugin/writer")
    roots = {}
    for identity, label in [("17", "Alpha"), ("21", "Beta")]:
        root = tmp_path / label.lower()
        candidate = workspace(root / ".scitex/writer")
        (candidate / "01_manuscript/contents/text.tex").write_text(label)
        roots[identity] = root
    projects = ObservedProjects()
    storage = Storage(roots)
    provider_module = ModuleType("_writer_hosting_provider_" + uuid4().hex)
    provider_module.projects = projects
    old_script_prefix, old_urlconf = get_script_prefix(), get_urlconf()
    set_script_prefix("/")
    set_urlconf(None)
    services._project_cache.clear()
    sys.modules[provider_module.__name__] = provider_module
    try:
        with override_settings(
            SCITEX_APP_MODE="hub",
            ROOT_URLCONF=urlconf_for(prefix),
            ALLOWED_HOSTS=["testserver"],
            MIDDLEWARE=[SessionIdentity.__module__ + ".SessionIdentity"],
            LOGIN_URL="/login/",
            SCITEX_PROJECT_PROVIDER=provider_module.__name__ + ".projects",
            SCITEX_PROJECT_STORAGE=storage,
        ):
            clear_url_caches()
            yield SimpleNamespace(
                client=Client(enforce_csrf_checks=True),
                roots=roots,
                projects=projects,
                storage=storage,
                prefix=prefix,
                api=prefix + "/v2",
                current=ActiveProject("17", "Alpha"),
            )
    finally:
        services._project_cache.clear()
        set_script_prefix(old_script_prefix)
        set_urlconf(old_urlconf)
        clear_url_caches()
        if sys.modules.get(provider_module.__name__) is provider_module:
            del sys.modules[provider_module.__name__]


def authorized_request(data=None, *, authenticated=True):
    request = RequestFactory().get("/workspace/content/", data or {})
    request.user = SimpleNamespace(is_authenticated=authenticated)
    return request


def content(mounted, data=None):
    return mounted.client.get(
        "/workspace/content/", data or {}, HTTP_AUDIT_SESSION="synthetic"
    )


def rendered_token(mounted):
    response = content(mounted)
    return re.search(
        r'name="writer-csrf-token" content="([^"]+)"', response.content.decode()
    ).group(1)


def manuscript(mounted, identity="17"):
    return mounted.roots[identity] / ".scitex/writer/01_manuscript/contents/text.tex"


def save(mounted, **headers):
    return mounted.client.post(
        mounted.api + "/api/file?project=17",
        {
            "path": "01_manuscript/contents/text.tex",
            "content": "Edited Alpha",
            "working_dir": str(mounted.roots["21"]),
        },
        content_type="application/json",
        HTTP_AUDIT_SESSION="synthetic",
        **headers,
    )


def test_generic_sdk_discovery_resolves_real_leaf_contract(mounted):
    # Arrange: the consumer's actual string schema, without importing Hub code.
    expected = dict.fromkeys(
        ["context_builder", "partial_template", "content_renderer", "api_policy_module", "hosted_api_dispatcher"],
        str,
    )
    # Act: read declarations through the genuine installed SDK consumer API.
    declarations = leaf_declarations("scitex_writer._django", expected)
    observed = {
        "keys": set(declarations),
        "builder": callable(import_string(declarations["context_builder"])),
        "renderer": callable(import_string(declarations["content_renderer"])),
        "dispatcher": callable(import_string(declarations["hosted_api_dispatcher"])),
        "partial": get_template(declarations["partial_template"]).origin.name.endswith(
            "/scitex_writer/_django/templates/writer/editor_partial.html"
        ),
    }
    # Assert: declarations are executable owning capabilities, not manifest guesses.
    assert observed == {"keys": set(expected), "builder": True, "renderer": True, "dispatcher": True, "partial": True}


def test_builder_returns_authorized_dict_and_preserves_newer_selection(mounted):
    # Arrange: content for Alpha while a newer navigation has selected Beta.
    request = authorized_request()
    original_query = request.GET.copy()
    # Act: call the actual public builder and render its genuine fallback partial.
    context = hosting.build_context(request, mounted.current)
    body = render_to_string("writer/editor_partial.html", context, request=request)
    # Assert: context, template and resource selection describe the same authorized root.
    assert (
        isinstance(context, dict),
        context["project_id"],
        context["project_dir"],
        context["stx_mount_prefix"],
        context["api_base"],
        'data-project-id="17"' in body,
        request.GET == original_query,
        mounted.projects.selected,
        mounted.projects.remembered,
    ) == (True, "17", str(mounted.roots["17"] / ".scitex/writer"), mounted.prefix, mounted.api + "/", True, True, "21", [])


@pytest.mark.parametrize("mounted", ["/plugin/writer", "/relocated/writer"], indirect=True)
def test_fragment_uses_server_mount_and_genuine_editor_without_standalone_shell(mounted):
    # Arrange: hostile client mount and working-dir hints on a generic content URL.
    query = {"api_base": "https://foreign.invalid/", "stx_mount": "/wrong", "BASE": "/wrong", "working_dir": str(mounted.roots["21"])}
    # Act: traverse the real URLconf, guard, project loader and templates.
    response = content(mounted, query)
    body = response.content.decode()
    # Assert: app marker and guarded API root remain distinct and server-owned.
    assert (
        isinstance(response, HttpResponse), response.status_code,
        re.search(r'name="stx-mount" content="([^"]*)"', body).group(1),
        re.search(r'data-api-base="([^"]*)"', body).group(1),
        re.search(r'data-project-id="([^"]*)"', body).group(1),
        body.count('class="writer-app"'), 'id="editor-container"' in body,
        'id="details-panel"' in body, 'writer/assets/index.js' in body,
        bool(document_shell_tokens(body)),
        "https://foreign.invalid/" in body,
        mounted.projects.selected, mounted.projects.remembered,
    ) == (True, 200, mounted.prefix, mounted.api + "/", "17", 1, True, True, True, False, False, "21", [])


def test_normal_full_editor_retains_real_document_shell(mounted):
    # Arrange: the existing mounted page route uses the normal standalone shell.
    # Act: render the genuine full editor through the real guarded page view.
    response = mounted.client.get(
        mounted.prefix + "/", {"project": "17"}, HTTP_AUDIT_SESSION="synthetic"
    )
    body = response.content.decode()
    # Assert: the same parser still detects every actual document-shell token.
    assert (
        response.status_code,
        document_shell_tokens(body),
        body.count('class="writer-app"'),
        'id="editor-container"' in body,
    ) == (200, {"doctype", "html", "head", "body"}, 1, True)


def test_script_prefix_is_present_once_in_app_marker_and_api_base(mounted):
    # Arrange: Django's actual script prefix, distinct from the generic content path.
    previous = get_script_prefix()
    set_script_prefix("/science/")
    try:
        # Act: use a genuine WSGI-style request with SCRIPT_NAME.
        with override_settings(
            ROOT_URLCONF=urlconf_for(
                mounted.prefix, content_mount="/science" + mounted.prefix + "/"
            )
        ):
            response = mounted.client.get(
                "/workspace/content/", SCRIPT_NAME="/science", HTTP_AUDIT_SESSION="synthetic"
            )
    finally:
        set_script_prefix(previous)
    body = response.content.decode()
    # Assert: trusted reverse already includes SCRIPT_NAME, with no extra concatenation.
    assert (
        response.status_code,
        re.search(r'name="stx-mount" content="([^"]*)"', body).group(1),
        re.search(r'data-api-base="([^"]*)"', body).group(1),
    ) == (200, "/science" + mounted.prefix, "/science" + mounted.api + "/")


def test_renderer_also_accepts_app_base_without_trailing_slash(mounted):
    # Arrange: the actual reversed app base is also a valid explicit host value.
    request = authorized_request()
    # Act: use the public guarded renderer, without the normal include's trailing slash.
    response = hosting.render_content(
        request, mounted.current, stx_mount=mounted.prefix
    )
    body = response.content.decode()
    # Assert: both supported forms produce the same genuine mount and private API family.
    assert (
        response.status_code,
        re.search(r'name="stx-mount" content="([^"]*)"', body).group(1),
        re.search(r'data-api-base="([^"]*)"', body).group(1),
    ) == (200, mounted.prefix, mounted.api + "/")


def test_per_request_urlconf_supplies_the_actual_leaf_mount(mounted):
    # Arrange: the default URLconf has no Writer include; request routing declares one.
    empty = ModuleType("writer_hosting_empty")
    empty.urlpatterns = []
    request = authorized_request()
    request.urlconf = urlconf_for("/per-request/writer")
    # Act: resolve the actual builder with trusted per-request URLconf provenance.
    with override_settings(ROOT_URLCONF=empty):
        context = hosting.build_context(request, mounted.current)
    # Assert: neither default routes nor the content URL supply API authority.
    assert (context["stx_mount_prefix"], context["api_base"]) == ("/per-request/writer", "/per-request/writer/v2/")


def test_thread_urlconf_supplies_the_actual_leaf_mount(mounted):
    # Arrange: normal Django thread URL routing differs from the configured default.
    previous = get_urlconf()
    set_urlconf(urlconf_for("/thread/writer"))
    try:
        # Act: call the genuine builder without a request-local override.
        context = hosting.build_context(authorized_request(), mounted.current)
    finally:
        set_urlconf(previous)
    # Assert: resolver and reverse use the same current trusted URLconf.
    assert (context["stx_mount_prefix"], context["api_base"]) == ("/thread/writer", "/thread/writer/v2/")


@pytest.mark.parametrize("stx_mount", [None, "", "/", "/other/v2", "api-root"])
def test_renderer_refuses_wrong_app_mount_before_loading_project(mounted, stx_mount):
    # Arrange: the host declares the app root; even Writer's API root is not that ABI.
    request = authorized_request()
    supplied_mount = mounted.api if stx_mount == "api-root" else stx_mount
    # Act: invoke the real guarded public renderer with a mismatching mount.
    response = hosting.render_content(request, mounted.current, stx_mount=supplied_mount)
    # Assert: the fragment is denied rather than silently rendering a root fallback.
    assert (response.status_code, bool(services._project_cache)) == (400, False)


def test_conflicting_duplicate_project_selector_stops_before_provider(mounted):
    # Arrange: the host supplies Alpha, while one duplicate selector asks for Beta.
    query = {"project": ["17", "21"]}
    # Act: resolve the real hosted resource through its CSRF/auth/project boundary.
    response = content(mounted, query)
    # Assert: no provider, storage, selection or cache load precedes this refusal.
    assert (response.status_code, mounted.projects.lookups, mounted.storage.path_calls, mounted.projects.selected, mounted.projects.remembered, bool(services._project_cache)) == (400, [], [], "21", [], False)


def test_matching_duplicate_project_selectors_do_not_remember_resource_selection(mounted):
    # Arrange: duplicate explicit selectors agree with the supplied host identity.
    query = {"project": ["17", "17"]}
    # Act: render the genuine authorized Alpha fragment.
    response = content(mounted, query)
    # Assert: successful content does not replace newer Beta navigation.
    assert (response.status_code, 'data-project-id="17"' in response.content.decode(), mounted.projects.selected, mounted.projects.remembered) == (200, True, "21", [])


def test_anonymous_builder_exposes_typed_401_without_project_state(mounted):
    # Arrange: the dictionary ABI receives an anonymous session.
    request = authorized_request(authenticated=False)
    error = None
    # Act: capture the actual typed refusal; unexpected exception types propagate.
    try:
        hosting.build_context(request, mounted.current)
    except host.AccessError as exc:
        error = exc
    # Assert: the typed 401 reaches no provider or project state.
    assert (isinstance(error, host.AccessError), getattr(error, "status", None), mounted.projects.lookups, mounted.storage.path_calls, bool(services._project_cache)) == (True, 401, [], [], False)


def test_anonymous_renderer_returns_resource_401_without_project_state(mounted):
    # Arrange: the HTTP resource receives no authenticated session.
    # Act: traverse the real renderer boundary through the generic content route.
    response = mounted.client.get("/workspace/content/")
    # Assert: a resource 401 reaches no provider or project state.
    assert (response.status_code, mounted.projects.lookups, mounted.storage.path_calls, bool(services._project_cache)) == (401, [], [], False)


@pytest.mark.parametrize("setting", ["SCITEX_PROJECT_PROVIDER", "SCITEX_PROJECT_STORAGE"])
def test_missing_host_capability_builder_is_typed_without_local_defaults(mounted, setting):
    # Arrange: the host deliberately supplies no requested capability.
    error = None
    with override_settings(**{setting: None}):
        # Act: capture the actual builder refusal without substituting a provider.
        try:
            hosting.build_context(authorized_request(), mounted.current)
        except host.CapabilityUnavailable as exc:
            error = exc
    # Assert: a typed capability failure cannot hide a cached local workspace.
    assert (isinstance(error, host.CapabilityUnavailable), bool(services._project_cache)) == (True, False)


@pytest.mark.parametrize("setting", ["SCITEX_PROJECT_PROVIDER", "SCITEX_PROJECT_STORAGE"])
def test_missing_host_capability_renderer_refuses_without_local_defaults(mounted, setting):
    # Arrange: the host deliberately supplies no requested capability.
    with override_settings(**{setting: None}):
        # Act: exercise the real renderer's HTTP failure mapping.
        response = content(mounted)
    # Assert: no successful partial or cached workspace hides the missing capability.
    assert (response.status_code, bool(services._project_cache)) == (503, False)


def test_supplied_current_project_is_a_selector_not_an_access_grant(mounted):
    # Arrange: a host object carries a foreign-looking root but an inaccessible id.
    current = SimpleNamespace(id="404", root=mounted.roots["21"])
    request = authorized_request()
    # Act: the real SDK must reauthorize the supplied id before touching that root.
    response = hosting.render_content(request, current, stx_mount=mounted.prefix)
    # Assert: passing a project object cannot manufacture a capability.
    assert (response.status_code, mounted.storage.path_calls, bool(services._project_cache)) == (404, [], False)


def test_missing_leaf_urlconf_builder_is_unavailable_before_project_load(mounted):
    # Arrange: the request's actual URLconf declares no Writer mount.
    candidate = urlconf_for("/first/writer")
    candidate.urlpatterns = []
    request = authorized_request()
    request.urlconf = candidate
    error = None
    # Act: capture the actual builder refusal without guessing a default route.
    try:
        hosting.build_context(request, mounted.current)
    except host.CapabilityUnavailable as exc:
        error = exc
    # Assert: a typed missing-mount failure precedes any cached project load.
    assert (isinstance(error, host.CapabilityUnavailable), bool(services._project_cache)) == (True, False)


def test_missing_leaf_urlconf_renderer_is_unavailable_before_project_load(mounted):
    # Arrange: the request's actual URLconf declares no Writer mount.
    candidate = urlconf_for("/first/writer")
    candidate.urlpatterns = []
    request = authorized_request()
    request.urlconf = candidate
    # Act: call the guarded renderer without guessing a default route.
    response = hosting.render_content(request, mounted.current, stx_mount=mounted.prefix)
    # Assert: a missing mount cannot fall back to a cached local workspace.
    assert (response.status_code, bool(services._project_cache)) == (503, False)


def test_ambiguous_leaf_urlconf_builder_is_unavailable_before_project_load(mounted):
    # Arrange: two actual Writer instances leave the trusted reverse ambiguous.
    candidate = urlconf_for("/first/writer")
    candidate.urlpatterns.append(
        path("second/writer/", include("scitex_writer._django.urls", namespace="second_writer"))
    )
    request = authorized_request()
    request.urlconf = candidate
    error = None
    # Act: capture the actual builder refusal without choosing an instance.
    try:
        hosting.build_context(request, mounted.current)
    except host.CapabilityUnavailable as exc:
        error = exc
    # Assert: the typed ambiguity refusal precedes any cached project load.
    assert (isinstance(error, host.CapabilityUnavailable), bool(services._project_cache)) == (True, False)


def test_ambiguous_leaf_urlconf_renderer_is_unavailable_before_project_load(mounted):
    # Arrange: two actual Writer instances leave the trusted reverse ambiguous.
    candidate = urlconf_for("/first/writer")
    candidate.urlpatterns.append(
        path("second/writer/", include("scitex_writer._django.urls", namespace="second_writer"))
    )
    request = authorized_request()
    request.urlconf = candidate
    # Act: call the guarded renderer without choosing a convenient instance.
    response = hosting.render_content(request, mounted.current, stx_mount=mounted.prefix)
    # Assert: an ambiguous reverse cannot fall back to a convenient route.
    assert (response.status_code, bool(services._project_cache)) == (503, False)


def test_workspace_symlink_escape_is_refused_by_genuine_project_loader(mounted):
    # Arrange: replace only Alpha's private workspace link with a link to Beta.
    original = mounted.roots["17"] / ".scitex/writer"
    original.rename(original.with_name("writer-original"))
    original.symlink_to(mounted.roots["21"] / ".scitex/writer", target_is_directory=True)
    # Act: render through the real capability, workspace resolver and root jail.
    response = content(mounted)
    # Assert: another project cannot supply the fragment's filesystem content.
    assert (response.status_code, bool(services._project_cache), manuscript(mounted, "21").read_text()) == (403, False, "Beta")


def test_missing_csrf_refuses_save_without_changing_files_or_selection(mounted):
    # Arrange: the real partial establishes the session cookie; omit its token.
    rendered_token(mounted)
    # Act: use the existing guarded API with a hostile body working_dir.
    response = save(mounted)
    # Assert: cookie alone cannot write Alpha or retarget Beta.
    assert (response.status_code, manuscript(mounted).read_text(), manuscript(mounted, "21").read_text(), mounted.projects.selected, mounted.projects.remembered) == (403, "Alpha", "Beta", "21", [])


def test_fragment_csrf_token_authorizes_only_confined_resource_save(mounted):
    # Arrange: take the actual token emitted by the new genuine partial.
    token = rendered_token(mounted)
    # Act: perform one real private file save through the unchanged v2 dispatcher.
    response = save(mounted, HTTP_X_CSRFTOKEN=token)
    # Assert: authorized Alpha changes while hostile body root and newer selection do not.
    assert (response.status_code, manuscript(mounted).read_text(), manuscript(mounted, "21").read_text(), mounted.projects.selected, mounted.projects.remembered) == (200, "Edited Alpha", "Beta", "21", [])


def test_cross_origin_write_with_fragment_token_preserves_confined_files(mounted):
    # Arrange: valid session and rendered token do not grant a foreign Origin.
    token = rendered_token(mounted)
    # Act: send the real guarded write with a cross-origin header.
    response = save(mounted, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://foreign.invalid")
    # Assert: token possession cannot bypass the leaf's CSRF boundary.
    assert (response.status_code, manuscript(mounted).read_text(), manuscript(mounted, "21").read_text()) == (403, "Alpha", "Beta")


def test_false_write_grant_with_fragment_token_stops_before_project_reload(mounted):
    # Arrange: acquire the token, then revoke genuine storage write permission.
    token = rendered_token(mounted)
    mounted.storage.writable = False
    mounted.storage.path_calls.clear()
    services._project_cache.clear()
    # Act: send the real API write with a valid CSRF token.
    response = save(mounted, HTTP_X_CSRFTOKEN=token)
    # Assert: SDK032 refuses before resolving a project path or loading cached state.
    assert (response.status_code, mounted.storage.path_calls, bool(services._project_cache), manuscript(mounted).read_text()) == (403, [], False, "Alpha")


def test_head_content_preserves_resource_contract_and_cookie(mounted):
    # Arrange: HEAD is a supported read-only generic content request.
    # Act: exercise the real URLconf and Django HEAD response handling.
    response = mounted.client.head("/workspace/content/", HTTP_AUDIT_SESSION="synthetic")
    # Assert: HEAD succeeds without content or navigation changes and issues CSRF state.
    assert (response.status_code, response.content, "csrftoken" in mounted.client.cookies, mounted.projects.selected, mounted.projects.remembered) == (200, b"", True, "21", [])


def test_unsafe_content_method_cannot_load_a_project_or_change_selection(mounted):
    # Arrange: use the genuine token so this tests the GET/HEAD-only contract.
    token = rendered_token(mounted)
    services._project_cache.clear()
    # Act: ask the actual hosted renderer to handle a protected POST.
    response = mounted.client.post(
        "/workspace/content/", HTTP_AUDIT_SESSION="synthetic", HTTP_X_CSRFTOKEN=token
    )
    # Assert: the renderer is read-only even when identity, CSRF and write grant are valid.
    assert (response.status_code, bool(services._project_cache), mounted.projects.selected, mounted.projects.remembered) == (405, False, "21", [])

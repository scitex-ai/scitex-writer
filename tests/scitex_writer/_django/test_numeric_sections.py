"""Legacy numeric section requests against synthetic SDK-authorized projects."""

from types import ModuleType, SimpleNamespace
from urllib.parse import urlencode

import pytest
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.test import Client, override_settings
from django.urls import include, path
from django.views.decorators.csrf import ensure_csrf_cookie
from scitex_sdk.ui import project_scope


class SessionIdentity:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        actor = request.headers.get("Synthetic-Actor", "")
        request.user = SimpleNamespace(is_authenticated=bool(actor), actor=actor)
        return self.get_response(request)


class Projects:
    selected = "17"

    def list_projects(self, request):
        ids = (
            ["17", "18", "19", "20", "21"]
            if request.user.actor in {"owner", "reader"}
            else []
        )
        return [
            project_scope.ProjectEntry(value, "Synthetic " + value) for value in ids
        ]

    def last_visited(self, request):
        return self.selected

    def remember(self, request, project_id):
        self.selected = project_id


projects = Projects()


class Storage:
    def __init__(self, roots):
        self.roots = roots
        self.writable = True

    def project_path(self, project_id, request):
        return self.roots.get(project_id)

    def can_write(self, project_id, request):
        return self.writable if request.user.actor == "owner" else False


@ensure_csrf_cookie
def csrf_fixture(request):
    return JsonResponse({"token": get_token(request)})


@pytest.fixture(params=["standalone", "default", "custom"])
def mounted(tmp_path, request):
    roots = {str(value): tmp_path / str(value) for value in range(17, 22)}
    for value in ["17", "18", "19", "21"]:
        roots[value].mkdir()
    ws = roots["17"] / ".scitex/writer"
    for name in [
        "00_shared",
        "01_manuscript/contents",
        "02_supplementary/contents",
        "03_revision/contents",
    ]:
        (ws / name).mkdir(parents=True)
    (ws / "01_manuscript/contents/abstract.tex").write_text("Synthetic abstract.")
    (roots["19"] / ".scitex/writer").mkdir(parents=True)
    beta = roots["21"] / ".scitex/writer"
    for name in [
        "00_shared",
        "01_manuscript/contents",
        "02_supplementary/contents",
        "03_revision/contents",
    ]:
        (beta / name).mkdir(parents=True)
    (beta / "01_manuscript/contents/abstract.tex").write_text("Synthetic beta.")
    projects.selected = "17"
    storage = Storage(roots)
    mode = request.param
    prefix = {
        "standalone": "/",
        "default": "/apps/writer/",
        "custom": "/custom/writer/",
    }[mode]
    module = ModuleType("writer_numeric_fixture_" + mode)
    module.urlpatterns = [
        path("csrf/", csrf_fixture),
        path(prefix.lstrip("/"), include("scitex_writer._django.urls")),
    ]
    with override_settings(
        SCITEX_APP_MODE="standalone" if mode == "standalone" else "hub",
        ROOT_URLCONF=module,
        ALLOWED_HOSTS=["testserver"],
        MIDDLEWARE=[__name__ + ".SessionIdentity"],
        SCITEX_PROJECT_PROVIDER=__name__ + ".projects",
        SCITEX_PROJECT_STORAGE=storage,
    ):
        yield SimpleNamespace(
            client=Client(enforce_csrf_checks=True),
            roots=roots,
            workspace=ws,
            storage=storage,
            prefix=prefix,
            mode=mode,
        )


def api_url(mounted, project_id, endpoint, **query):
    if mounted.mode == "standalone":
        query.setdefault("working_dir", str(mounted.roots[str(project_id)]))
    base = f"{mounted.prefix}api/project/{project_id}/{endpoint}/"
    return base + ("?" + urlencode(query, doseq=True) if query else "")


def section_url(mounted, project_id, section="abstract", **query):
    return api_url(mounted, project_id, "section/" + section, **query)


def get(mounted, project_id, section="abstract"):
    return mounted.client.get(
        section_url(mounted, project_id, section), HTTP_SYNTHETIC_ACTOR="owner"
    )


def test_written_section_uses_the_legacy_renderable_payload(mounted):
    response = get(mounted, 17)
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["success"] is True and payload["content"] == "Synthetic abstract."
    assert payload["section_name"] == "abstract" and payload["section_id"] == "abstract"
    assert payload["doc_type"] == "manuscript" and payload["workspace_ready"] is True
    assert payload["missing"] is False


def test_unwritten_section_is_empty_ready_content_without_creating_a_file(mounted):
    response = get(mounted, 17, "discussion")
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["success"] is True and payload["content"] == ""
    assert payload["missing"] is True and payload["workspace_ready"] is True
    assert payload["file_path"] is None
    assert not (mounted.workspace / "01_manuscript/contents/discussion.tex").exists()


def test_project_without_a_workspace_reports_readiness_without_scaffolding(mounted):
    response = get(mounted, 18)
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["success"] is True and payload["content"] == ""
    assert payload["workspace_ready"] is False and payload["missing"] is True
    assert list(mounted.roots["18"].iterdir()) == []


def test_half_created_workspace_has_the_same_honest_readiness_payload(mounted):
    response = get(mounted, 19)
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["success"] is True and payload["content"] == ""
    assert payload["workspace_ready"] is False and payload["missing"] is True
    assert list((mounted.roots["19"] / ".scitex/writer").iterdir()) == []


def test_csrf_authorized_write_into_an_unready_workspace_is_a_conflict(mounted):
    csrf = mounted.client.get("/csrf/").json()["token"]
    response = mounted.client.post(
        section_url(mounted, 18),
        {"content": "Too early."},
        content_type="application/json",
        HTTP_SYNTHETIC_ACTOR="owner",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 409, response.content
    assert response.json()["workspace_ready"] is False
    assert list(mounted.roots["18"].iterdir()) == []


def csrf(mounted):
    return mounted.client.get("/csrf/").json()["token"]


def post(mounted, project_id, content, *, actor="owner", **body):
    return mounted.client.post(
        section_url(mounted, project_id),
        {"content": content, **body},
        content_type="application/json",
        HTTP_SYNTHETIC_ACTOR=actor,
        HTTP_X_CSRFTOKEN=csrf(mounted),
    )


def test_written_sections_round_trip_with_real_session_csrf(mounted):
    assert post(mounted, 17, "Edited synthetic abstract.").status_code == 200
    assert get(mounted, 17).json()["content"] == "Edited synthetic abstract."
    assert (
        mounted.workspace / "01_manuscript/contents/abstract.tex"
    ).read_text() == "Edited synthetic abstract."
    assert (
        mounted.roots["21"] / ".scitex/writer/01_manuscript/contents/abstract.tex"
    ).read_text() == "Synthetic beta."


def test_missing_project_directory_is_observed_without_creating_it(mounted):
    response = get(mounted, 20)
    assert response.status_code == 200
    assert response.json()["workspace_ready"] is False
    assert not mounted.roots["20"].exists()


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
@pytest.mark.parametrize("endpoint", ["section/abstract", "manuscript-status"])
def test_host_missing_root_refusal_is_not_downgraded_to_readiness(mounted, endpoint):
    expected_root = mounted.roots["20"]
    mounted.storage.roots["20"] = None
    response = mounted.client.get(
        api_url(mounted, 20, endpoint), HTTP_SYNTHETIC_ACTOR="owner"
    )
    assert response.status_code == 404
    assert not expected_root.exists()


@pytest.mark.parametrize("mounted", ["default"], indirect=True)
def test_rendered_writer_brand_assets_resolve_after_wheel_install(mounted):
    from html.parser import HTMLParser

    from django.contrib.staticfiles import finders

    class Icons(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paths = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "link" and attrs.get("rel") in {"icon", "apple-touch-icon"}:
                href = attrs["href"]
                if href.startswith("/static/writer/"):
                    self.paths.append(href.removeprefix("/static/"))

    response = mounted.client.get(
        mounted.prefix + "?project=17", HTTP_SYNTHETIC_ACTOR="owner"
    )
    assert response.status_code == 200
    icons = Icons()
    icons.feed(response.content.decode())
    assert "writer/favicon.svg" in icons.paths
    assert "writer/favicon-180x180.png" in icons.paths
    for asset_path in icons.paths:
        assert finders.find(asset_path) is not None, asset_path


def test_empty_existing_section_is_distinct_from_missing_content(mounted):
    (mounted.workspace / "01_manuscript/contents/abstract.tex").write_text("")
    payload = get(mounted, 17).json()
    assert payload["content"] == "" and payload["missing"] is False
    assert payload["workspace_ready"] is True


@pytest.mark.parametrize(
    "section,relative",
    [
        ("shared/title", "00_shared/title.tex"),
        ("supplementary/methods", "02_supplementary/contents/methods.tex"),
        ("revision/editor", "03_revision/contents/editor.tex"),
    ],
)
def test_hierarchical_section_ids_use_the_leaf_workspace_layout(
    mounted, section, relative
):
    target = mounted.workspace / relative
    target.write_text("Synthetic " + section)
    response = get(mounted, 17, section)
    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == "Synthetic " + section
    assert (
        payload["section_id"] == section
        and payload["section_name"] == section.split("/")[1]
    )
    assert payload["file_path"] == str(target)


@pytest.mark.parametrize(
    "body",
    [
        [],
        None,
        {"content": None},
        {"content": 123},
        {"content": "X", "doc_type": None},
        {"content": "X", "doc_type": {}},
        {"content": "X", "doc_type": []},
        {"content": "X", "doc_type": "unknown"},
    ],
)
def test_invalid_write_payload_cannot_modify_a_section(mounted, body):
    response = mounted.client.post(
        section_url(mounted, 17),
        body,
        content_type="application/json",
        HTTP_SYNTHETIC_ACTOR="owner",
        HTTP_X_CSRFTOKEN=csrf(mounted),
    )
    assert response.status_code == 400, response.content
    assert (
        mounted.workspace / "01_manuscript/contents/abstract.tex"
    ).read_text() == "Synthetic abstract."


def test_malformed_json_is_a_client_error(mounted):
    response = mounted.client.post(
        section_url(mounted, 17),
        "{",
        content_type="application/json",
        HTTP_SYNTHETIC_ACTOR="owner",
        HTTP_X_CSRFTOKEN=csrf(mounted),
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "section",
    [
        "manuscript/../abstract",
        "../abstract",
        "unknown/title",
        "manuscript/.secret",
        "abstract/delete",
        "create",
    ],
)
def test_path_escape_and_unimplemented_management_routes_never_become_saves(
    mounted, section
):
    response = get(mounted, 17, section)
    assert response.status_code == 400, response.content
    assert sorted(
        p.name for p in (mounted.workspace / "01_manuscript/contents").iterdir()
    ) == ["abstract.tex"]


@pytest.mark.parametrize(
    "endpoint,method", [("section/abstract", "put"), ("manuscript-status", "post")]
)
def test_methods_outside_the_legacy_contract_are_refused(mounted, endpoint, method):
    response = getattr(mounted.client, method)(
        api_url(mounted, 17, endpoint),
        {},
        content_type="application/json",
        HTTP_SYNTHETIC_ACTOR="owner",
        HTTP_X_CSRFTOKEN=csrf(mounted),
    )
    assert response.status_code == 405, response.content


@pytest.mark.parametrize(
    "filename", ["missing.pdf", "../escape.pdf", "/absolute.pdf", "wrong.txt"]
)
def test_readiness_does_not_claim_nonexistent_or_invalid_pdf_names(mounted, filename):
    response = mounted.client.get(
        api_url(mounted, 17, "manuscript-status", pdf=filename),
        HTTP_SYNTHETIC_ACTOR="owner",
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "exists": True, "has_pdf": False}


@pytest.mark.parametrize(
    "directory,filename",
    [
        (".preview", "preview-abstract.pdf"),
        ("01_manuscript", "manuscript.pdf"),
        ("preview_output", "preview-light.pdf"),
    ],
)
def test_readiness_observes_existing_writer_pdf_locations(mounted, directory, filename):
    target = mounted.workspace / directory / filename
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(b"%PDF synthetic fixture bytes")
    response = mounted.client.get(
        api_url(mounted, 17, "manuscript-status", pdf=filename),
        HTTP_SYNTHETIC_ACTOR="owner",
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "exists": True, "has_pdf": True}
    assert target.read_bytes() == b"%PDF synthetic fixture bytes"


def test_unready_manuscript_status_is_an_explicit_normal_response(mounted):
    response = mounted.client.get(
        api_url(mounted, 18, "manuscript-status"), HTTP_SYNTHETIC_ACTOR="owner"
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "exists": False, "has_pdf": False}


@pytest.mark.parametrize("bad_file", ["directory", "non-text"])
def test_real_file_read_failures_remain_server_errors(mounted, bad_file):
    target = mounted.workspace / "01_manuscript/contents/abstract.tex"
    target.unlink()
    if bad_file == "directory":
        target.mkdir()
    else:
        target.write_bytes(b"\xff\xfe\xff")
    response = get(mounted, 17)
    assert response.status_code == 500
    assert response.json() == {"success": False, "error": "Unable to access section."}


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
def test_url_project_switch_cannot_leak_stored_project_content(mounted):
    projects.selected = "17"
    assert get(mounted, 21).json()["content"] == "Synthetic beta."
    assert projects.selected == "21"
    assert get(mounted, 17).json()["content"] == "Synthetic abstract."
    assert projects.selected == "17"


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
@pytest.mark.parametrize("choice", ["21", ["17", "21"]])
def test_query_project_substitution_is_refused_before_remembering(mounted, choice):
    projects.selected = "17"
    response = mounted.client.get(
        section_url(mounted, 17, project=choice), HTTP_SYNTHETIC_ACTOR="owner"
    )
    assert response.status_code == 400
    assert projects.selected == "17"


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
def test_caller_working_directory_and_body_project_cannot_redirect_saves(mounted):
    response = mounted.client.post(
        section_url(mounted, 17, working_dir=str(mounted.roots["21"])),
        {
            "content": "Scoped edit.",
            "project": "21",
            "working_dir": str(mounted.roots["21"]),
        },
        content_type="application/json",
        HTTP_SYNTHETIC_ACTOR="owner",
        HTTP_X_CSRFTOKEN=csrf(mounted),
    )
    assert response.status_code == 200
    assert get(mounted, 17).json()["content"] == "Scoped edit."
    assert get(mounted, 21).json()["content"] == "Synthetic beta."


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
@pytest.mark.parametrize("endpoint", ["section/abstract", "manuscript-status"])
def test_anonymous_and_inaccessible_projects_never_reach_files(mounted, endpoint):
    url = api_url(mounted, 17, endpoint)
    assert mounted.client.get(url).status_code == 401
    assert mounted.client.get(url, HTTP_SYNTHETIC_ACTOR="stranger").status_code == 404
    assert (
        mounted.client.get(
            api_url(mounted, 999, endpoint), HTTP_SYNTHETIC_ACTOR="owner"
        ).status_code
        == 404
    )


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
@pytest.mark.parametrize(
    "missing", ["SCITEX_PROJECT_PROVIDER", "SCITEX_PROJECT_STORAGE"]
)
def test_missing_sdk_capability_returns_unavailable_without_local_fallback(
    mounted, missing
):
    with override_settings(**{missing: ""}):
        response = mounted.client.get(
            section_url(mounted, 17, working_dir=str(mounted.roots["21"])),
            HTTP_SYNTHETIC_ACTOR="owner",
        )
    assert response.status_code == 503


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
@pytest.mark.parametrize("writable", [False, None, 0, 1, "true"])
def test_write_authority_requires_literal_true(mounted, writable):
    mounted.storage.writable = writable
    assert post(mounted, 17, "Forbidden.").status_code == 403
    assert get(mounted, 17).json()["content"] == "Synthetic abstract."


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
def test_read_only_collaborator_can_read_but_cannot_save(mounted):
    assert (
        mounted.client.get(
            section_url(mounted, 17), HTTP_SYNTHETIC_ACTOR="reader"
        ).status_code
        == 200
    )
    assert post(mounted, 17, "Forbidden.", actor="reader").status_code == 403
    assert get(mounted, 17).json()["content"] == "Synthetic abstract."


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
def test_csrf_refusal_cannot_select_another_project_or_write(mounted):
    projects.selected = "17"
    response = mounted.client.post(
        section_url(mounted, 21),
        {"content": "Forbidden."},
        content_type="application/json",
        HTTP_SYNTHETIC_ACTOR="owner",
    )
    assert response.status_code == 403
    assert projects.selected == "17"
    assert (
        mounted.roots["21"] / ".scitex/writer/01_manuscript/contents/abstract.tex"
    ).read_text() == "Synthetic beta."


def test_cross_origin_save_is_refused_even_with_a_session_token(mounted):
    response = mounted.client.post(
        section_url(mounted, 17),
        {"content": "Forbidden."},
        content_type="application/json",
        HTTP_SYNTHETIC_ACTOR="owner",
        HTTP_X_CSRFTOKEN=csrf(mounted),
        HTTP_ORIGIN="https://foreign.invalid",
    )
    assert response.status_code == 403
    assert get(mounted, 17).json()["content"] == "Synthetic abstract."


@pytest.mark.parametrize("mounted", ["default", "custom"], indirect=True)
def test_workspace_and_section_symlinks_cannot_escape_the_capability(mounted):
    target = mounted.workspace / "01_manuscript/contents/abstract.tex"
    target.unlink()
    target.symlink_to(
        mounted.roots["21"] / ".scitex/writer/01_manuscript/contents/abstract.tex"
    )
    assert get(mounted, 17).status_code == 400
    target.unlink()
    escaped = mounted.roots["18"] / ".scitex"
    escaped.mkdir()
    (escaped / "writer").symlink_to(
        mounted.roots["21"] / ".scitex/writer", target_is_directory=True
    )
    assert get(mounted, 18).status_code == 403


def test_readiness_never_follows_an_outbound_pdf_symlink(mounted):
    target = mounted.roots["21"] / ".scitex/writer/01_manuscript/manuscript.pdf"
    target.write_bytes(b"%PDF synthetic foreign fixture")
    (mounted.workspace / "01_manuscript/manuscript.pdf").symlink_to(target)
    response = mounted.client.get(
        api_url(mounted, 17, "manuscript-status", pdf="manuscript.pdf"),
        HTTP_SYNTHETIC_ACTOR="owner",
    )
    assert response.json()["has_pdf"] is False


@pytest.mark.parametrize("section", ["compiled_tex", "compiled_pdf"])
def test_virtual_compiled_sections_refuse_unimplemented_compatibility(mounted, section):
    response = get(mounted, 17, section)
    assert response.status_code == 501
    assert response.json()["success"] is False
    assert not (
        mounted.workspace / "01_manuscript/contents" / f"{section}.tex"
    ).exists()


@pytest.mark.parametrize("mode", ["invalid", "Standalone", None])
def test_invalid_host_mode_refuses_readiness_and_section_requests(mounted, mode):
    with override_settings(SCITEX_APP_MODE=mode):
        for endpoint in ["section/abstract", "manuscript-status"]:
            response = mounted.client.get(
                api_url(mounted, 17, endpoint), HTTP_SYNTHETIC_ACTOR="owner"
            )
            assert response.status_code == 503

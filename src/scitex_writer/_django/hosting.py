"""Leaf-owned workspace content and trusted URL mounting declarations.

The host supplies project capabilities through the SDK. No Hub models,
filesystem defaults, navigation URL or client mount values are consulted.
"""

from copy import copy
from types import SimpleNamespace

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, get_resolver, get_urlconf, reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from scitex_sdk import host
from scitex_sdk.ui.mount import mount_prefix

from ._host_boundary import project_boundary, standalone
from .views import _editor_context, _get_project


def _mounted_app_prefix(request):
    """Reverse the leaf's server route, independent of the content request."""
    urlconf = getattr(request, "urlconf", None) or get_urlconf()
    if len(get_resolver(urlconf).app_dict.get("writer", [])) != 1:
        raise host.CapabilityUnavailable("Writer URL mount is missing or ambiguous")
    try:
        editor_url = reverse("writer:editor", urlconf=urlconf)
    except NoReverseMatch:
        raise host.CapabilityUnavailable("Writer URL mount is unavailable") from None
    return mount_prefix(SimpleNamespace(path=editor_url))


def _selected_request(request, current_project=None, **kwargs):
    """Use only the supplied project's identity, reauthorized by the SDK."""
    if current_project is None:
        return request
    project_id = getattr(current_project, "id", None)
    if (
        isinstance(project_id, bool)
        or not isinstance(project_id, (str, int))
        or not str(project_id)
    ):
        raise host.AccessError("Current project has no usable identity", 400)
    project_id = str(project_id)
    if any(value != project_id for value in request.GET.getlist("project")):
        raise host.AccessError("Project selector conflicts with current project", 400)
    selected = copy(request)
    selected.GET = request.GET.copy()
    selected.GET["project"] = project_id
    return selected


def _content_context(request, current_project, app_mount):
    project = _get_project(request)
    return {
        **_editor_context(request, project),
        "current_project": current_project,
        "app_scope": "project",
        "writer_app_mode": "standalone" if standalone() else "hub",
        "app_header_rendered": True,
        "api_base": app_mount + "/v2/",
        "stx_mount_prefix": app_mount,
        "stx_mount_declared": True,
    }


def build_context(request, current_project=None):
    """Return a genuine authorized partial context or raise a typed SDK error.

    Generic hosts must map these errors, rather than treating a missing mount as
    permission to fall back to an unguarded template. Resource context building
    does not remember a project or initialize a manuscript.
    """
    if request.method not in {"GET", "HEAD"}:
        raise host.AccessError("GET or HEAD required", 405)
    if not standalone() and not getattr(
        getattr(request, "user", None), "is_authenticated", False
    ):
        raise host.AccessError("Authentication required", 401)
    app_mount = _mounted_app_prefix(request)
    selected = _selected_request(request, current_project)
    if not standalone():
        selected.writer_project_access = host.project_access(
            selected, write=False, remember=False
        )
    return _content_context(selected, current_project, app_mount)


@project_boundary(project_selector=_selected_request)
@ensure_csrf_cookie
def render_content(request, current_project=None, *, stx_mount):
    """Render Writer under the host-proven leaf URLconf's base mount.

    The host never needs to know Writer's v2 API route. Its supplied mount is
    checked against the leaf's own server reverse before constructing URLs.
    """
    if request.method not in {"GET", "HEAD"}:
        raise host.AccessError("GET or HEAD required", 405)
    if not isinstance(stx_mount, str):
        raise host.AccessError("Hosted mount does not match leaf URLconf", 400)
    # Generic include mounts carry a trailing slash; SDK mount markers do not.
    stx_mount = stx_mount.removesuffix("/")
    if stx_mount != _mounted_app_prefix(request):
        raise host.AccessError("Hosted mount does not match leaf URLconf", 400)
    return HttpResponse(
        render_to_string(
            "writer/editor_partial.html",
            _content_context(request, current_project, stx_mount),
            request=request,
        )
    )

"""Leaf-owned authorization and session CSRF for standalone and plugin routes."""

from copy import copy
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import resolve_url
from django.views.decorators.csrf import csrf_protect
from scitex_sdk import host


def standalone() -> bool:
    # A host that forgets to declare its mode must never expose local paths.
    mode = getattr(settings, "SCITEX_APP_MODE", "hub")
    if mode not in ("hub", "standalone"):
        raise host.CapabilityUnavailable("Host mode is invalid")
    return mode == "standalone"


def project_boundary(*, page=False, project_from_url=False, project_selector=None):
    """Authorize every request before loading cached state or invoking handlers.

    Host settings provide project identity, storage and permissions. HTTP
    working_dir values and process-global local defaults have no authority in
    plugin mode. CSRF also applies when included without host middleware.
    Page navigation remembers explicit selection; resource requests resolve
    their authorized project without replacing a newer navigation selection.
    """

    def decorate(view):
        @wraps(view)
        def authorized(request, *args, **kwargs):
            if not standalone():
                # Project resolution may remember an explicit selection. Keep
                # that side effect behind CSRF validation for unsafe requests.
                capability_request = request
                if project_selector is not None:
                    capability_request = project_selector(request, *args, **kwargs)
                if project_from_url:
                    # Numeric legacy URLs are an explicit selector, never an
                    # authorization grant or a fallback to the stored project.
                    project_id = str(kwargs["project_id"])
                    if any(
                        value != project_id for value in request.GET.getlist("project")
                    ):
                        raise host.AccessError(
                            "Project selector conflicts with URL", 400
                        )
                    capability_request = copy(request)
                    capability_request.GET = request.GET.copy()
                    capability_request.GET["project"] = project_id
                request.writer_project_access = host.project_access(
                    capability_request,
                    write=request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"},
                    remember=page,
                )
            return view(request, *args, **kwargs)

        protected = csrf_protect(authorized)

        @wraps(view)
        def guarded(request, *args, **kwargs):
            try:
                if not standalone() and not getattr(
                    getattr(request, "user", None), "is_authenticated", False
                ):
                    raise host.AccessError("Authentication required", 401)
                return protected(request, *args, **kwargs)
            except host.AccessError as exc:
                if page and exc.status == 401:
                    login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
                    target = resolve_url(login_url)
                    separator = "&" if "?" in target else "?"
                    return HttpResponseRedirect(
                        target
                        + separator
                        + urlencode({"next": request.get_full_path()})
                    )
                return JsonResponse({"error": str(exc)}, status=exc.status)
            except host.CapabilityUnavailable:
                return JsonResponse(
                    {"error": "Project capability is unavailable"}, status=503
                )

        return guarded

    return decorate

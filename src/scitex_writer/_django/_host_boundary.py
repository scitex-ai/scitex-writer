"""Leaf-owned authorization and session CSRF for standalone and plugin routes."""

from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import resolve_url
from django.views.decorators.csrf import csrf_protect
from scitex_sdk import host


def standalone() -> bool:
    # A host that forgets to declare its mode must never expose local paths.
    return getattr(settings, "SCITEX_APP_MODE", "hub") == "standalone"


def project_boundary(*, page=False):
    """Authorize every request before loading cached state or invoking handlers.

    Host settings provide project identity, storage and permissions. HTTP
    working_dir values and process-global local defaults have no authority in
    plugin mode. CSRF also applies when included without host middleware.
    """

    def decorate(view):
        @wraps(view)
        def authorized(request, *args, **kwargs):
            if not standalone():
                # Project resolution may remember an explicit selection. Keep
                # that side effect behind CSRF validation for unsafe requests.
                request.writer_project_access = host.project_access(
                    request, write=request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}
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
                        target + separator + urlencode({"next": request.get_full_path()})
                    )
                return JsonResponse({"error": str(exc)}, status=exc.status)
            except host.CapabilityUnavailable:
                return JsonResponse({"error": "Project capability is unavailable"}, status=503)

        return guarded

    return decorate

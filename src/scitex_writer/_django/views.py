#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Views for the scitex-writer editor Django app.

Mirrors the figrecipe/_django/views.py pattern: one `editor_page` serves
the SPA shell; `api_dispatch` is a catch-all that routes `<path:endpoint>`
to the HANDLERS registry (with a few parameterized fallbacks for
`api/claims/<id>` and `api/claims/<id>/chain`).
"""

from __future__ import annotations

import logging
import os

from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt

from .handlers import (
    HANDLERS,
    handle_add_annotation,
    handle_add_claim,
    handle_citation,
    handle_claim_chain,
    handle_get_claim,
    handle_list_annotations,
    handle_list_claims,
    handle_remove_claim,
)
from .services import get_or_create_project
from ..workspace_layout import NotAWriterWorkspaceError

logger = logging.getLogger(__name__)


def _app_config():
    """The registered writer Django app config (its manifest is the SDK's view)."""
    from django.apps import apps

    return apps.get_app_config("writer_editor")


def _leaf_identity() -> dict:
    """Title + version for the leaf header, read through the scitex-app manifest.

    WHICH VERSION: the LEAF's, from the app's own `manifest.json` (`version`),
    which `ScitexAppConfig.app_version` reads — the same field a host reads when
    it wants to know what it mounted, and the reason the key is pinned to
    pyproject by a test. It is deliberately NOT the host's version (the hub's
    header showed `v0.20.0-alpha` for a writer build) and not a hand-written
    string in a source comment: both are claims about someone else's package.
    """
    config = _app_config()
    manifest = config.manifest
    return {
        "writer_version": config.app_version,
        "writer_label": manifest.get("label", "Writer"),
    }


def _project_picker_available() -> bool:
    """True when the host registered the `scitex_project_picker` tag library.

    Writer's picker PARTIAL ships in this package; its TAG comes from the host
    (the hub ships it and includes the partial into its header). Standalone
    `scitex-writer gui` has no such library and serves no project list, and
    `{% load %}`ing a library that is not installed is a hard
    TemplateSyntaxError — so the slot is rendered only when the tag resolves.
    """
    from django.template import engines

    return "scitex_project_picker" in engines["django"].engine.template_libraries


def _get_project(request):
    """Resolve the current project from ?working_dir= or SCITEX_WRITER_WORKING_DIR.

    The unprefixed spelling is retired (fleet convention is
    SCITEX_WRITER_<X>); ._legacy_env raises at startup rather than letting a
    stranded one be ignored here.
    """
    working_dir = request.GET.get("working_dir") or os.environ.get(
        "SCITEX_WRITER_WORKING_DIR", ""
    )
    if not working_dir:
        return None
    try:
        return get_or_create_project(working_dir)
    except FileNotFoundError:
        logger.warning("[Writer] Project not found: %s", working_dir)
        return None
    except NotAWriterWorkspaceError:
        # A directory that is neither a project root (no .scitex/writer under
        # it) nor a workspace (no 00_shared/ in it). The load point (#389
        # follow-up) now raises this named error instead of letting the
        # downstream compile fail with a bare FileNotFoundError on
        # root/00_shared/... — map it to the same 400 the missing-dir case
        # returns so the UI reads a clean "no project" state.
        logger.warning(
            "[Writer] working_dir is not a writer project or workspace: %s",
            working_dir,
        )
        return None


def _app_label(base: str) -> str:
    """Tab title per the fleet SCITEX_APP_MODE convention.

    The operator wants the browser tab alone to distinguish hub-embedded
    from standalone. scitex-hub reads the same setting and defaults to
    "hub" (hub PR #357); these settings only boot the standalone server,
    so writer defaults to "standalone" and appends the marker.
    """
    from django.conf import settings as django_settings

    mode = getattr(django_settings, "SCITEX_APP_MODE", "standalone")
    return f"{base} (standalone)" if mode == "standalone" else base


def _favicon_href() -> str:
    """Writer's own brand mark, for the scitex-ui shell's icon link.

    scitex-ui 0.7.0 made the shell's ``<link rel="icon">`` UNCONDITIONAL,
    falling back to the shared SciTeX mark when a view supplies no
    ``favicon_href`` (scitex_ui/templates/scitex_ui/_branding_head.html).
    Writer supplied none, so every page emitted the shared mark ON TOP OF
    writer's own links -- untidy rather than broken, since the shell's link
    precedes ``extra_css`` and ours won.

    Passing this makes the shell emit WRITER's mark, so there is exactly one
    bare ``rel="icon"``. The sized PNG variants and the apple-touch-icon stay
    in each template's ``extra_css``: the shell has no way to express
    ``sizes=`` or ``apple-touch-icon``, and a single shared SVG is not a
    substitute for a 180x180 home-screen icon.
    """
    from django.templatetags.static import static

    return static("writer/favicon.svg")


#: Writer fills exactly one pane of the scitex-ui shell — the module pane, where
#: `.writer-app` mounts. The other three are declared unused so the shell
#: collapses them and the editor gets the full viewport.
#:
#: This USED to be a stylesheet in editor.css targeting
#: `.workspace-three-col > .ws-ai-pane` and siblings: scitex-ui's private class
#: names, which they are free to rename and which would have broken writer
#: silently, with no way for either side to notice. Two of those five selectors
#: were already wrong by the time they were removed. `panes=` is an API
#: scitex-ui is obliged not to break, and an unknown key or state raises rather
#: than quietly leaving a pane visible.
#:
#: "unused" EVERYWHERE, with no SCITEX_APP_MODE gate, on scitex-hub's own
#: answer (card writer-adopt-pane-contract-drop-css-hide-hack-20260718,
#: 2026-08-02): hub does not embed writer's _django at all — it ships its own
#: writer app with its own stylesheet and its own `.writer-app-container` — so
#: there is no cloud caller whose panes this could hide. The old CSS comment
#: claiming "cloud deployments override this" described a coupling that never
#: existed.
_SHELL_PANES = {"ai": "unused", "files": "unused", "viewer": "unused"}


def _shell_context(base_title: str) -> dict:
    """The scitex-ui shell context for a writer page.

    ``shell_context`` sets ``app_label`` from the tool name, which would
    clobber writer's ``(standalone)`` tab marker, so that key is merged back
    ON TOP rather than the helper's dict being taken wholesale.

    Parameters
    ----------
    base_title : str
        Tab title before the mode marker, e.g. ``"SciTeX Writer"``.

    Returns
    -------
    dict
        Shell context ready to merge into a template context.
    """
    from scitex_ui.branding import shell_context

    context = shell_context(
        "Writer",
        favicon_href=_favicon_href(),
        panes=_SHELL_PANES,
    )
    context["app_label"] = _app_label(base_title)
    return context


def editor_page(request):
    """Serve the editor shell page."""
    project = _get_project(request)
    project_dir = str(project.project_dir) if project else ""
    html = render_to_string(
        "writer/editor.html",
        {
            "app_name": "writer",
            "project_dir": project_dir,
            "dark_mode": project.dark_mode if project else False,
            # The leaf header: our title + OUR version, and the picker slot only
            # when the host registered its tag library.
            **_leaf_identity(),
            "project_picker_available": _project_picker_available(),
            # A host embedding this page renders its own header and includes
            # writer/_app_header.html; that host sets this True so the page
            # keeps exactly one header. Standalone renders the leaf one.
            "app_header_rendered": False,
            **_shell_context("SciTeX Writer"),
        },
        request=request,
    )
    return HttpResponse(html)


@csrf_exempt
def api_dispatch(request, endpoint):
    """Dispatch API calls to handler functions.

    Resolution order:
      1. Exact match in HANDLERS (with method allow-list check).
      2. Parameterized claim endpoints: `api/claims/<id>`, `api/claims/<id>/chain`.
      3. 404.
    """
    project = _get_project(request)
    if project is None:
        return JsonResponse(
            {"error": "No project loaded. Pass ?working_dir=<path>."}, status=400
        )

    entry = HANDLERS.get(endpoint)
    if entry is not None:
        handler, allowed_methods = entry
        if request.method not in allowed_methods:
            return JsonResponse(
                {"error": f"Method {request.method} not allowed"}, status=405
            )

        # Method-dispatched endpoints where HANDLERS maps to None
        if endpoint == "api/claims":
            handler = (
                handle_add_claim if request.method == "POST" else handle_list_claims
            )
        elif endpoint == "api/annotations":
            handler = (
                handle_add_annotation
                if request.method == "POST"
                else handle_list_annotations
            )

        try:
            return handler(request, project)
        except Exception as exc:
            logger.exception("[Writer] API error on /%s", endpoint)
            return JsonResponse({"error": str(exc)}, status=500)

    # Parameterized: api/claims/<id> or api/claims/<id>/chain
    if endpoint.startswith("api/claims/"):
        rest = endpoint[len("api/claims/") :].strip("/")
        parts = rest.split("/") if rest else []
        if len(parts) == 1:
            claim_id = parts[0]
            try:
                if request.method == "DELETE":
                    return handle_remove_claim(request, project, claim_id)
                return handle_get_claim(request, project, claim_id)
            except Exception as exc:
                logger.exception("[Writer] claim %s", claim_id)
                return JsonResponse({"error": str(exc)}, status=500)
        if len(parts) == 2 and parts[1] == "chain":
            try:
                return handle_claim_chain(request, project, parts[0])
            except Exception as exc:
                logger.exception("[Writer] claim chain %s", parts[0])
                return JsonResponse({"error": str(exc)}, status=500)

    # Parameterized: api/citation/<cite_key>
    if endpoint.startswith("api/citation/"):
        cite_key = endpoint[len("api/citation/") :].strip("/")
        if cite_key:
            try:
                return handle_citation(request, project, cite_key)
            except Exception as exc:
                logger.exception("[Writer] citation %s", cite_key)
                return JsonResponse({"error": str(exc)}, status=500)

    return JsonResponse({"error": f"Unknown endpoint: {endpoint}"}, status=404)


def viewer_page(request):
    """Serve the read-only viewer (PDF + claim overlays + DAG)."""
    project = _get_project(request)
    project_dir = str(project.project_dir) if project else ""
    html = render_to_string(
        "writer/viewer.html",
        {
            "app_name": "writer",
            "project_dir": project_dir,
            **_shell_context("SciTeX Writer — Viewer"),
        },
        request=request,
    )
    return HttpResponse(html)
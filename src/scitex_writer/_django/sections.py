"""Leaf-owned compatibility for numeric project section/readiness requests.

These reads observe existing files. They never initialize a workspace, attach
Writer (which can scaffold templates), link a library or start compilation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from scitex_logging import getLogger
from scitex_sdk import host

from scitex_writer.workspace_layout import (
    NotAWriterWorkspaceError,
    resolve_workspace,
    workspace_dir,
)

from ._host_boundary import project_boundary, standalone

logger = getLogger(__name__)
_DOCUMENT_DIRS = {
    "manuscript": "01_manuscript/contents",
    "supplementary": "02_supplementary/contents",
    "revision": "03_revision/contents",
    "shared": "00_shared",
}
_UNSET = object()
_FULL_PDFS = {
    "manuscript.pdf": "01_manuscript",
    "supplementary.pdf": "02_supplementary",
    "revision.pdf": "03_revision",
}


def _workspace(request) -> Path:
    if standalone():
        selected = request.GET.get("working_dir") or os.environ.get(
            "SCITEX_WRITER_WORKING_DIR", ""
        )
        if not selected:
            raise host.AccessError("No local Writer project selected", 400)
        root = Path(selected).resolve()
    else:
        root = request.writer_project_access.root
    try:
        workspace = resolve_workspace(root).resolve()
    except (FileNotFoundError, NotAWriterWorkspaceError):
        # A registered project may have no workspace yet. Preserve its expected
        # location for readiness observation; no directory is created here.
        workspace = workspace_dir(root).resolve()
    if not standalone() and not workspace.is_relative_to(root):
        raise host.AccessError("Writer workspace must be inside this project", 403)
    return workspace


def _within(workspace: Path, relative: str) -> Path:
    target = (workspace / relative).resolve()
    if not target.is_relative_to(workspace):
        raise host.AccessError("Invalid section path", 400)
    return target


def _ready(workspace: Path) -> bool:
    # The existing Writer attach contract requires these three directories.
    # An unrelated filesystem/read error remains an error, never empty success.
    return all(
        _within(workspace, name).is_dir()
        for name in ("01_manuscript", "02_supplementary", "03_revision")
    )


def _section(section_id: str, doc_type):
    parts = section_id.split("/")
    category = "manuscript"
    if len(parts) == 2:
        category, name = parts
    elif len(parts) == 1:
        name = parts[0]
    else:
        raise host.AccessError("Invalid section path", 400)
    chosen = category if doc_type is _UNSET else doc_type
    if (
        category not in _DOCUMENT_DIRS
        or not isinstance(chosen, str)
        or chosen not in _DOCUMENT_DIRS
        or not name
        or name.startswith(".")
        or "\\" in name
        or "\0" in name
        or name == "create"
    ):
        raise host.AccessError("Invalid section path", 400)
    return name, chosen


def _payload(
    section_id, name, doc_type, *, content="", ready=False, missing=True, file_path=None
):
    return {
        "success": True,
        "content": content,
        "section_name": name,
        "section_id": section_id,
        "doc_type": doc_type,
        "file_path": str(file_path) if file_path else None,
        "missing": missing,
        "workspace_ready": ready,
    }


@project_boundary(project_from_url=True)
@require_http_methods(["GET", "POST"])
def section_content(request, project_id, section_name):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        if not isinstance(data, dict) or not isinstance(data.get("content"), str):
            return JsonResponse(
                {"success": False, "error": "Text content is required"}, status=400
            )
        content, doc_type = data["content"], data.get("doc_type", _UNSET)
    else:
        doc_type = request.GET.get("doc_type", _UNSET)
    name, doc_type = _section(section_name, doc_type)
    if name in {"compiled_tex", "compiled_pdf"}:
        return JsonResponse(
            {
                "success": False,
                "error": "Compiled-section compatibility is unavailable",
            },
            status=501,
        )
    try:
        workspace = _workspace(request)
        target = _within(workspace, f"{_DOCUMENT_DIRS[doc_type]}/{name}.tex")
        if not _ready(workspace):
            if request.method == "POST":
                return JsonResponse(
                    {
                        "success": False,
                        "error": "workspace not initialized for this project",
                        "workspace_ready": False,
                    },
                    status=409,
                )
            return JsonResponse(_payload(section_name, name, doc_type))
        missing = not target.exists()
        if request.method == "GET":
            content = "" if missing else target.read_text(encoding="utf-8")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            missing = False
        return JsonResponse(
            _payload(
                section_name,
                name,
                doc_type,
                content=content,
                ready=True,
                missing=missing,
                file_path=None if missing else target,
            )
        )
    except (OSError, UnicodeError):
        logger.exception("Writer section operation failed")
        return JsonResponse(
            {"success": False, "error": "Unable to access section."}, status=500
        )


@project_boundary(project_from_url=True)
@require_http_methods(["GET"])
def manuscript_status(request, project_id):
    try:
        workspace = _workspace(request)
        exists = _within(workspace, "01_manuscript").is_dir()
        filename = request.GET.get("pdf", "")
        has_pdf = False
        if (
            exists
            and filename
            and Path(filename).name == filename
            and filename.endswith(".pdf")
            and "\\" not in filename
            and "\0" not in filename
        ):
            locations = [".preview", "preview_output"]
            if filename in _FULL_PDFS:
                locations.insert(1, _FULL_PDFS[filename])
            for directory in locations:
                try:
                    candidate = _within(workspace, f"{directory}/{filename}")
                except host.AccessError:
                    continue
                if candidate.is_file():
                    has_pdf = True
                    break
        return JsonResponse({"success": True, "exists": exists, "has_pdf": has_pdf})
    except (OSError, UnicodeError):
        logger.exception("Writer readiness observation failed")
        return JsonResponse(
            {"success": False, "error": "Unable to inspect manuscript."}, status=500
        )

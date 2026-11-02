"""Authorized section preview adapter over the package's snippet compiler."""

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from django.http import FileResponse, JsonResponse

from .files import _resolve_safe

_PREVIEW_ID = re.compile(r"[a-f0-9]{32}")


def _artifact(project, preview_id):
    if not isinstance(preview_id, str) or not _PREVIEW_ID.fullmatch(preview_id):
        return None
    return _resolve_safe(project.project_dir, f".preview/section-{preview_id}.pdf")


def handle_section_preview(request, project):
    """Compile the current buffer without saving or overwriting manuscript PDF."""
    from scitex_writer import __version__, compile as writer_compile

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Expected a JSON object"}, status=400)
    path = data.get("section_path")
    content = data.get("content")
    if not isinstance(path, str) or not isinstance(content, str):
        return JsonResponse({"error": "Section path and content are required"}, status=400)
    section = _resolve_safe(project.project_dir, path)
    if section is None or _resolve_safe(project.project_dir, ".preview") is None:
        return JsonResponse({"error": "Access denied"}, status=403)
    if not section.is_file() or section.suffix != ".tex":
        return JsonResponse({"error": "Section is not a TeX file"}, status=400)
    if len(content.encode("utf-8")) > 1_000_000:
        return JsonResponse({"error": "Section preview is too large"}, status=413)
    color = "dark" if data.get("dark_mode") else "light"
    preview_id = hashlib.sha256(
        json.dumps([path, content, color, __version__], ensure_ascii=False).encode()
    ).hexdigest()[:32]
    artifact = _artifact(project, preview_id)
    if artifact is None:
        return JsonResponse({"error": "Access denied"}, status=403)
    if artifact.is_file():
        return JsonResponse({"success": True, "preview_id": preview_id, "section_path": path, "cached": True})
    result = writer_compile.content(
        content, project_dir=str(project.project_dir), color_mode=color,
        name=f"section-{preview_id}", timeout=60,
    )
    try:
        if not result.success or not artifact.is_file():
            return JsonResponse({
                "success": False, "section_path": path,
                "error": result.message or "Section preview failed",
                "log": (result.stdout + "\n" + result.stderr)[-400_000:],
            })
        return JsonResponse({"success": True, "preview_id": preview_id, "section_path": path, "cached": False})
    finally:
        # The existing compiler creates a private scratch directory per call.
        # Keep only its atomically published project preview PDF.
        if result.temp_dir:
            scratch = Path(result.temp_dir)
            if scratch.parent.resolve() == Path(tempfile.gettempdir()).resolve() and scratch.name.startswith(f"scitex_content_section-{preview_id}_"):
                shutil.rmtree(scratch)


def handle_section_pdf(request, project):
    preview_id = request.GET.get("preview_id", "")
    artifact = _artifact(project, preview_id)
    if artifact is None:
        return JsonResponse({"error": "Access denied"}, status=403)
    if not artifact.is_file():
        return JsonResponse({"error": "Section preview not found"}, status=404)
    return FileResponse(
        artifact.open("rb"), content_type="application/pdf",
        as_attachment=request.GET.get("download") == "1", filename="section.pdf",
    )

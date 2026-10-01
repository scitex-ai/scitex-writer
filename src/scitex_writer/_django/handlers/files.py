#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""File tree and file read/write handlers."""

from __future__ import annotations

import json
from pathlib import Path

from django.http import JsonResponse

_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".tox",
    "archive",
    "GITIGNORED",
    ".claude",
}
_SKIP_EXTENSIONS = {".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".synctex.gz"}


def _build_file_tree(root: Path, rel_base: Path | None = None, ancestors=frozenset()) -> list:
    if rel_base is None:
        rel_base = root
    resolved = root.resolve()
    if not resolved.is_relative_to(rel_base.resolve()) or resolved in ancestors:
        return []
    ancestors = ancestors | {resolved}

    try:
        items = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return []

    entries = []
    for item in items:
        try:
            inside = item.resolve().is_relative_to(rel_base.resolve())
        except (OSError, RuntimeError):
            continue
        if not inside:
            continue
        if item.name.startswith(".") and item.name != ".gitignore":
            continue
        if item.name in _SKIP_DIRS:
            continue

        rel_path = str(item.relative_to(rel_base))
        if item.is_dir():
            entries.append(
                {
                    "name": item.name,
                    "path": rel_path,
                    "type": "directory",
                    "children": _build_file_tree(item, rel_base, ancestors),
                }
            )
        else:
            if item.suffix in _SKIP_EXTENSIONS:
                continue
            entries.append(
                {
                    "name": item.name,
                    "path": rel_path,
                    "type": "file",
                    "extension": item.suffix,
                }
            )
    return entries


def _resolve_safe(project_dir: Path, rel_path: str) -> Path | None:
    """Return the resolved absolute path if it is inside project_dir, else None."""
    abs_path = (project_dir / rel_path).resolve()
    try:
        abs_path.relative_to(project_dir)
    except ValueError:
        return None
    return abs_path


def handle_list_files(request, project):
    return JsonResponse({"tree": _build_file_tree(project.project_dir)})


def handle_file(request, project):
    """GET: read file; POST: save file."""
    if request.method == "POST":
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        rel_path = data.get("path", "")
        content = data.get("content", "")
        if not rel_path:
            return JsonResponse({"error": "No path specified"}, status=400)

        file_path = _resolve_safe(project.project_dir, rel_path)
        if file_path is None:
            return JsonResponse({"error": "Access denied"}, status=403)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return JsonResponse({"success": True, "path": rel_path})
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)

    rel_path = request.GET.get("path", "")
    if not rel_path:
        return JsonResponse({"error": "No path specified"}, status=400)

    file_path = _resolve_safe(project.project_dir, rel_path)
    if file_path is None:
        return JsonResponse({"error": "Access denied"}, status=403)
    if not file_path.exists():
        return JsonResponse({"error": "File not found"}, status=404)
    if not file_path.is_file():
        return JsonResponse({"error": "Not a file"}, status=400)

    try:
        return JsonResponse(
            {
                "path": rel_path,
                "content": file_path.read_text(encoding="utf-8"),
                "name": file_path.name,
                "extension": file_path.suffix,
            }
        )
    except UnicodeDecodeError:
        return JsonResponse({"error": "Binary file cannot be displayed"}, status=400)


def handle_sections(request, project):
    doc_type = request.GET.get("doc_type", "manuscript")
    dir_map = {
        "manuscript": "01_manuscript/contents",
        "supplementary": "02_supplementary/contents",
        "revision": "03_revision/contents",
        "shared": "00_shared",
    }
    content_dir = project.project_dir / dir_map.get(doc_type, "01_manuscript/contents")
    sections = []
    if content_dir.exists():
        for f in sorted(content_dir.glob("*.tex")):
            sections.append(
                {
                    "name": f.stem,
                    "path": str(f.relative_to(project.project_dir)),
                    "filename": f.name,
                }
            )
    return JsonResponse({"doc_type": doc_type, "sections": sections})

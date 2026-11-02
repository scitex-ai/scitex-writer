#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figures + tables handlers — list scitex-writer's caption_and_media files.

A figure/table "entry" in a scitex-writer project is a `.tex` file under
`{doc}/contents/figures/caption_and_media/` or the parallel `tables/`
directory. The compile script auto-discovers them; the writer UI needs the
same list to populate the insert-figure / insert-table panels.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from django.http import FileResponse, Http404, JsonResponse

from scitex_writer._ports.thumbnails import (
    ensure_thumbnail,
    find_media_for_stem,
)


def _list_media(
    project_dir: Path,
    doc_type: str,
    kind: str,
    *,
    thumbnail_base: str = "/api/thumbnail",
    selector: dict[str, str] | None = None,
) -> list[dict]:
    """kind: 'figures' | 'tables'."""
    doc_map = {
        "manuscript": "01_manuscript",
        "supplementary": "02_supplementary",
        "revision": "03_revision",
    }
    doc_root = project_dir / doc_map.get(doc_type, "01_manuscript")
    media_dir = doc_root / "contents" / kind / "caption_and_media"
    if not media_dir.exists():
        return []

    entries = []
    for tex in sorted(media_dir.glob("*.tex")):
        label = _extract_label(tex)
        media = find_media_for_stem(media_dir, tex.stem)
        thumb_url: str | None = None
        if media is not None:
            try:
                media_rel = media.resolve().relative_to(project_dir.resolve())
                query = {"kind": kind, "path": str(media_rel), **(selector or {})}
                thumb_url = thumbnail_base + "?" + urlencode(query)
            except ValueError:
                thumb_url = None
        entries.append(
            {
                "name": tex.stem,
                "path": str(tex.relative_to(project_dir)),
                "label": label,
                "insert": f"\\ref{{{label}}}" if label else f"\\ref{{{tex.stem}}}",
                "media_path": str(media.relative_to(project_dir)) if media else None,
                "media_ext": media.suffix.lower() if media else None,
                "thumbnail_url": thumb_url,
            }
        )
    return entries


def _extract_label(tex_path: Path) -> str | None:
    """Parse `\\label{...}` out of the .tex file."""
    try:
        text = tex_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    import re

    match = re.search(r"\\label\{([^}]+)\}", text)
    return match.group(1) if match else None


def _thumbnail_context(request, project) -> dict:
    """Use this request's mount and already-authorized project selection."""
    access = getattr(request, "writer_project_access", None)
    selector = (
        {"project": str(access.id)}
        if access is not None
        else {"working_dir": str(project.project_dir)}
    )
    return {
        "thumbnail_base": request.path.rstrip("/").rsplit("/", 1)[0] + "/thumbnail",
        "selector": selector,
    }


def handle_figures(request, project):
    doc_type = request.GET.get("doc_type", "manuscript")
    return JsonResponse(
        {
            "doc_type": doc_type,
            "figures": _list_media(
                project.project_dir,
                doc_type,
                "figures",
                **_thumbnail_context(request, project),
            ),
        }
    )


def handle_tables(request, project):
    doc_type = request.GET.get("doc_type", "manuscript")
    return JsonResponse(
        {
            "doc_type": doc_type,
            "tables": _list_media(
                project.project_dir,
                doc_type,
                "tables",
                **_thumbnail_context(request, project),
            ),
        }
    )


def handle_thumbnail(request, project):
    """Serve a cached thumbnail PNG for a project-relative media path."""
    kind = request.GET.get("kind", "figures")
    rel = request.GET.get("path", "")
    if kind not in ("figures", "tables") or not rel:
        raise Http404("bad thumbnail request")
    source = (project.project_dir / rel).resolve()
    try:
        source.relative_to(project.project_dir.resolve())
    except ValueError:
        raise Http404("path escapes project")
    if not source.is_file():
        raise Http404("source missing")
    thumb = ensure_thumbnail(project.project_dir, kind, source)
    if thumb is None or not thumb.is_file():
        raise Http404("thumbnail unavailable")
    return FileResponse(thumb.open("rb"), content_type="image/png")

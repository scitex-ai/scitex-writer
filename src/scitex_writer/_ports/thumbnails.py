"""Thumbnail service — Pillow-based, generic across figure/table sources.

Writer aggregates figure/table media files by extension (PNG, JPG, PDF,
SVG, CSV, TSV, TEX, ...), and renders a thumbnail PNG to a cache dir:

    <project>/00_shared/thumbnails/figures/<sha1>.png
    <project>/00_shared/thumbnails/tables/<sha1>.png

Cache key is ``sha1(abs_path + mtime)`` so the thumbnail invalidates
on mtime change. A sibling project like figrecipe may populate the
same cache using the same hash — first writer wins, no coordination.

This module knows nothing about figrecipe or any specific image
provider. It treats the filesystem as the source of truth.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional

from scitex_logging import getLogger

logger = getLogger(__name__)


# Extensions we can thumbnail, in preference order (highest quality first).
IMAGE_EXTS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".jfif",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".tif",
    ".ico",
    ".heic",
    ".avif",
)
VECTOR_EXTS = (".svg", ".pdf", ".eps", ".ps")
DATA_EXTS = (".csv", ".tsv", ".xlsx", ".xls", ".ods")

THUMB_EDGE = 256


def thumbnail_key(source: Path) -> str:
    """sha1 of absolute path + mtime. Stable cache key."""
    try:
        mtime = source.stat().st_mtime_ns
    except OSError:
        mtime = 0
    return hashlib.sha1(f"{source.resolve()}|{mtime}".encode()).hexdigest()


def thumbnail_path(project_dir: Path, kind: str, source: Path) -> Path:
    cache_dir = project_dir / "00_shared" / "thumbnails" / kind
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{thumbnail_key(source)}.png"


def find_media_for_stem(media_root: Path, stem: str) -> Optional[Path]:
    """Find the media file matching ``stem`` under ``media_root``.

    Walks the directory and its subdirs (e.g. ``jpg_for_compilation/``).
    Returns the first match in preference order (raster > vector > data).
    """
    if not media_root.is_dir():
        return None

    candidates_by_ext: dict[str, Path] = {}
    for path in media_root.rglob(f"{stem}.*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in IMAGE_EXTS + VECTOR_EXTS + DATA_EXTS:
            candidates_by_ext.setdefault(ext, path)

    for ext in IMAGE_EXTS + VECTOR_EXTS + DATA_EXTS:
        if ext in candidates_by_ext:
            return candidates_by_ext[ext]
    return None


def ensure_thumbnail(project_dir: Path, kind: str, source: Path) -> Optional[Path]:
    """Generate a thumbnail for ``source`` if missing. Returns the path or None."""
    target = thumbnail_path(project_dir, kind, source)
    if target.exists() and target.stat().st_size > 0:
        return target
    try:
        _render_thumbnail(source, target)
    except Exception as exc:
        logger.warning("Thumbnail failed for %s: %s", source, exc)
        return None
    return target if target.exists() else None


def _render_thumbnail(source: Path, target: Path) -> None:
    ext = source.suffix.lower()
    if ext in IMAGE_EXTS:
        _render_image(source, target)
    elif ext == ".pdf":
        _render_pdf(source, target)
    elif ext == ".svg":
        _render_svg(source, target)
    elif ext in DATA_EXTS:
        _render_data_preview(source, target)
    else:
        _render_placeholder(source, target, label=ext.strip(".").upper())


def _render_image(source: Path, target: Path) -> None:
    from PIL import Image

    with Image.open(source) as img:
        img.thumbnail((THUMB_EDGE, THUMB_EDGE))
        img.convert("RGBA").save(target, format="PNG")


def _render_pdf(source: Path, target: Path) -> None:
    """Render the first page of a PDF via pdftoppm if available; else placeholder."""
    import shutil

    if shutil.which("pdftoppm"):
        tmp_prefix = target.with_suffix("")
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-singlefile",
                "-scale-to",
                str(THUMB_EDGE),
                str(source),
                str(tmp_prefix),
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
        produced = tmp_prefix.with_suffix(".png")
        if produced.exists() and produced != target:
            produced.rename(target)
        return
    _render_placeholder(source, target, label="PDF")


def _render_svg(source: Path, target: Path) -> None:
    """Render SVG via rsvg-convert if available; else placeholder."""
    import shutil

    if shutil.which("rsvg-convert"):
        subprocess.run(
            [
                "rsvg-convert",
                "-w",
                str(THUMB_EDGE),
                "-o",
                str(target),
                str(source),
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return
    _render_placeholder(source, target, label="SVG")


def _render_data_preview(source: Path, target: Path) -> None:
    """Render a CSV/TSV/XLSX/ODS as a styled 5-row table preview.

    Port of scitex-cloud's `generate_table_thumbnail`: pandas reads the
    top-left 5×4 corner, matplotlib renders to PNG. Falls back to a
    text placeholder if pandas/matplotlib are unavailable or the file
    can't be parsed.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd
    except ImportError:
        _render_placeholder(source, target, label=source.suffix.strip(".").upper())
        return

    ext = source.suffix.lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(source, nrows=5)
        elif ext == ".tsv":
            df = pd.read_csv(source, sep="\t", nrows=5)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(source, nrows=5)
        elif ext == ".ods":
            df = pd.read_excel(source, engine="odf", nrows=5)
        else:
            _render_placeholder(source, target, label=source.suffix.strip(".").upper())
            return
    except Exception as exc:
        logger.warning("Table preview failed for %s: %s", source, exc)
        _render_placeholder(source, target, label=source.suffix.strip(".").upper())
        return

    if df is None or df.empty:
        _render_placeholder(source, target, label="EMPTY")
        return

    if len(df.columns) > 4:
        df = df.iloc[:, :4]
        df["..."] = "..."

    df = df.map(lambda x: str(x)[:15] + "…" if len(str(x)) > 15 else str(x))

    fig, ax = plt.subplots(figsize=(5, 3), facecolor="white")
    ax.axis("tight")
    ax.axis("off")

    table = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        cellLoc="center",
        loc="center",
        bbox=[0, 0, 1, 1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2)

    for (row, _col), cell in table.get_celld().items():
        cell.set_edgecolor("#cccccc")
        cell.set_linewidth(1)
        cell.PAD = 0.05
        if row == 0:
            cell.set_facecolor("#4A90E2")
            cell.set_text_props(weight="bold", color="white", size=9)
        else:
            cell.set_facecolor("#f8f9fa" if row % 2 == 0 else "white")
            cell.set_text_props(size=8)

    fig.savefig(
        target,
        format="png",
        dpi=120,
        bbox_inches="tight",
        pad_inches=0.15,
        facecolor="white",
        edgecolor="none",
    )
    plt.close(fig)


def _render_placeholder(source: Path, target: Path, label: str) -> None:
    """Fallback: draw a text label with Pillow for unrendered formats."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (THUMB_EDGE, THUMB_EDGE), (245, 245, 245, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (THUMB_EDGE - 1, THUMB_EDGE - 1)], outline=(200, 200, 200))
    try:
        from PIL import ImageFont

        font = ImageFont.load_default()
    except Exception:
        font = None
    text = label
    bbox = draw.textbbox((0, 0), text, font=font) if font else (0, 0, 50, 10)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((THUMB_EDGE - w) // 2, (THUMB_EDGE - h) // 2),
        text,
        fill=(120, 120, 120, 255),
        font=font,
    )
    name = source.stem[:20]
    if name:
        draw.text((8, THUMB_EDGE - 20), name, fill=(80, 80, 80, 255), font=font)
    img.save(target, format="PNG")

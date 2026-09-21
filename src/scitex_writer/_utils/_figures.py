#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_utils/_figures.py

"""
Figure listing and conversion utilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from scitex_logging import getLogger

logger = getLogger(__name__)


def list_figures(
    project_dir: Union[str, Path],
    extensions: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    List all figures in a writer project.

    Parameters
    ----------
    project_dir : str or Path
        Path to writer project directory
    extensions : list of str, optional
        Figure extensions to include. Default: common image formats.

    Returns
    -------
    list of dict
        List of figure info dicts with path, name, size, etc.

    Examples
    --------
    >>> figures = list_figures("my_paper")
    >>> for fig in figures:
    ...     print(fig['name'], fig['size_kb'])
    """
    project_dir = Path(project_dir)
    if not project_dir.exists():
        raise FileNotFoundError(f"Project directory not found: {project_dir}")

    if extensions is None:
        extensions = [
            ".png",
            ".jpg",
            ".jpeg",
            ".pdf",
            ".eps",
            ".svg",
            ".tif",
            ".tiff",
            ".ppt",
            ".pptx",
        ]

    # Search in common figure locations
    figure_dirs = [
        project_dir / "00_shared" / "figures",
        project_dir / "00_shared" / "figs",
        project_dir / "01_manuscript" / "figures",
        project_dir / "01_manuscript" / "figs",
        project_dir / "02_supplementary" / "figures",
        project_dir / "02_supplementary" / "figs",
    ]

    figures = []
    for fig_dir in figure_dirs:
        if fig_dir.exists():
            for ext in extensions:
                for filepath in fig_dir.glob(f"*{ext}"):
                    stat = filepath.stat()
                    figures.append(
                        {
                            "path": str(filepath),
                            "name": filepath.name,
                            "stem": filepath.stem,
                            "extension": filepath.suffix,
                            "size_bytes": stat.st_size,
                            "size_kb": round(stat.st_size / 1024, 2),
                            "directory": str(fig_dir),
                            "relative_path": str(filepath.relative_to(project_dir)),
                        }
                    )

    # Sort by name
    figures.sort(key=lambda x: x["name"])

    logger.info(f"Found {len(figures)} figures in {project_dir}")
    return figures


def convert_figure(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    dpi: int = 300,
    quality: int = 95,
) -> Dict[str, Any]:
    """
    Convert figure between formats.

    Parameters
    ----------
    input_path : str or Path
        Input figure path
    output_path : str or Path
        Output figure path (format determined by extension)
    dpi : int, default 300
        Resolution for rasterization (PDF/SVG to raster)
    quality : int, default 95
        JPEG quality (1-100)

    Returns
    -------
    dict
        Conversion result with paths and sizes

    Examples
    --------
    >>> convert_figure("fig1.pdf", "fig1.png", dpi=300)
    >>> convert_figure("fig1.png", "fig1.jpg", quality=90)
    """

    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    input_ext = input_path.suffix.lower()
    output_ext = output_path.suffix.lower()

    # Handle PDF input
    if input_ext == ".pdf":
        _convert_pdf_to_image(input_path, output_path, dpi, quality)
    else:
        # Standard image conversion with PIL
        _convert_image_to_image(input_path, output_path, quality)

    # Get output size
    output_stat = output_path.stat()

    return {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "input_size_kb": round(input_path.stat().st_size / 1024, 2),
        "output_size_kb": round(output_stat.st_size / 1024, 2),
        "dpi": dpi,
        "quality": quality if output_ext in [".jpg", ".jpeg"] else None,
    }


def _convert_pdf_to_image(
    input_path: Path, output_path: Path, dpi: int, quality: int
) -> None:
    """Convert PDF to image format."""
    try:
        import fitz
        from PIL import Image
    except ImportError:
        raise ImportError("PyMuPDF and Pillow required for PDF conversion")

    doc = fitz.open(input_path)
    page = doc[0]
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)

    output_ext = output_path.suffix.lower()
    if output_ext in [".jpg", ".jpeg"]:
        # Save as PNG first, then convert
        import io

        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(str(output_path), "JPEG", quality=quality)
    else:
        pix.save(str(output_path))

    doc.close()


def _convert_image_to_image(input_path: Path, output_path: Path, quality: int) -> None:
    """Convert image to image format using PIL."""
    from PIL import Image

    img = Image.open(input_path)
    output_ext = output_path.suffix.lower()

    # Handle format-specific conversions
    if output_ext in [".jpg", ".jpeg"]:
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(str(output_path), "JPEG", quality=quality)
    else:
        img.save(str(output_path))


__all__ = ["list_figures", "convert_figure"]

# EOF

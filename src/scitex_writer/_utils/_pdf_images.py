#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_utils/_pdf_images.py

"""
PDF to image rendering utilities.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from scitex_logging import getLogger

logger = getLogger(__name__)


def pdf_to_images(
    pdf_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    pages: Optional[Union[int, List[int]]] = None,
    dpi: int = 600,
    format: str = "png",
    prefix: str = "page",
) -> List[Dict[str, Any]]:
    """
    Render PDF pages as images.

    Parameters
    ----------
    pdf_path : str or Path
        Path to PDF file
    output_dir : str or Path, optional
        Directory to save images. If None, uses temp directory.
    pages : int or list of int, optional
        Page(s) to render (0-indexed). If None, renders all pages.
    dpi : int, default 600
        Resolution in DPI
    format : str, default 'png'
        Output format ('png', 'jpg', 'jpeg')
    prefix : str, default 'page'
        Filename prefix

    Returns
    -------
    list of dict
        List of dicts with image info:
        - page: Page number (0-indexed)
        - path: Path to saved image
        - width: Image width in pixels
        - height: Image height in pixels

    Examples
    --------
    >>> # Render first page as thumbnail
    >>> images = pdf_to_images("paper.pdf", pages=0, dpi=72)
    >>> print(images[0]['path'])

    >>> # Render all pages at high resolution
    >>> images = pdf_to_images("paper.pdf", "output/", dpi=300)
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError(
            "PyMuPDF required for PDF to image conversion. "
            "Install with: pip install PyMuPDF"
        )

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Setup output directory
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="pdf_images_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    # Normalize format
    format = format.lower()
    if format == "jpeg":
        format = "jpg"

    # Calculate zoom factor for DPI (default PDF DPI is 72)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    results = []
    doc = fitz.open(pdf_path)

    try:
        if pages is None:
            pages_to_render = range(len(doc))
        elif isinstance(pages, int):
            pages_to_render = [pages]
        else:
            pages_to_render = pages

        for page_num in pages_to_render:
            if page_num < 0 or page_num >= len(doc):
                logger.warning(f"Page {page_num} out of range, skipping")
                continue

            pdf_page = doc[page_num]
            pix = pdf_page.get_pixmap(matrix=matrix)

            # Generate filename
            filename = f"{prefix}_{page_num + 1:03d}.{format}"
            filepath = output_dir / filename

            # Save image
            if format == "png":
                pix.save(str(filepath))
            else:  # jpg
                _save_as_jpg(pix, filepath)

            results.append(
                {
                    "page": page_num,
                    "path": str(filepath),
                    "width": pix.width,
                    "height": pix.height,
                    "dpi": dpi,
                    "format": format,
                }
            )

            logger.debug(f"Rendered page {page_num + 1} to {filepath}")

    finally:
        doc.close()

    logger.info(f"Rendered {len(results)} pages from {pdf_path}")
    return results


def _save_as_jpg(pix, filepath: Path) -> None:
    """Save pixmap as JPEG, handling conversion from PNG."""
    try:
        import io

        from PIL import Image

        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
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
        img.save(str(filepath), "JPEG", quality=95)
    except ImportError:
        # Fallback to PNG if PIL not available
        filepath = filepath.with_suffix(".png")
        pix.save(str(filepath))


def pdf_thumbnail(
    pdf_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    page: int = 0,
    width: int = 200,
    format: str = "png",
) -> Dict[str, Any]:
    """
    Generate a thumbnail from a PDF page.

    Parameters
    ----------
    pdf_path : str or Path
        Path to PDF file
    output_path : str or Path, optional
        Path to save thumbnail. If None, auto-generates.
    page : int, default 0
        Page to use for thumbnail (0-indexed)
    width : int, default 200
        Thumbnail width in pixels (height auto-calculated)
    format : str, default 'png'
        Output format ('png', 'jpg')

    Returns
    -------
    dict
        Thumbnail info with path, width, height

    Examples
    --------
    >>> thumb = pdf_thumbnail("paper.pdf")
    >>> print(thumb['path'])
    """
    try:
        import fitz
    except ImportError:
        raise ImportError(
            "PyMuPDF required for PDF thumbnails. Install with: pip install PyMuPDF"
        )

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)

    try:
        if page < 0 or page >= len(doc):
            raise IndexError(f"Page {page} out of range. PDF has {len(doc)} pages.")

        pdf_page = doc[page]

        # Calculate zoom to achieve desired width
        page_rect = pdf_page.rect
        zoom = width / page_rect.width
        matrix = fitz.Matrix(zoom, zoom)

        pix = pdf_page.get_pixmap(matrix=matrix)

        # Determine output path
        if output_path is None:
            output_dir = Path(tempfile.mkdtemp(prefix="pdf_thumb_"))
            output_path = output_dir / f"{pdf_path.stem}_thumb.{format}"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save
        pix.save(str(output_path))

        return {
            "path": str(output_path),
            "width": pix.width,
            "height": pix.height,
            "source_page": page,
            "source_pdf": str(pdf_path),
            "format": format,
        }

    finally:
        doc.close()


__all__ = ["pdf_to_images", "pdf_thumbnail"]

# EOF

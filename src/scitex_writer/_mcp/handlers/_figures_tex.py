#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_figures_tex.py

r"""The LaTeX half of the figure pipeline (port of ``04_compilation.src``).

Everything that writes ``.tex``, in the order ``process`` runs it:

* :func:`compile_legends`          -- ``compiled_dir/NN_*.tex`` from the caption bodies.
* :func:`handle_figure_visibility` -- the ``.figures_enabled`` marker.
* :func:`compile_figure_tex_files` -- assemble ``FINAL.tex`` + the ``_placeable/`` copies.

Two behaviours the shell pinned and this port keeps verbatim:

* the NO-figures fallback header emits **no figure float** -- only LaTeX comments;
  base.tex is the single source of the "Figures" ``\section*`` / ``\pdfbookmark``,
  so an empty-figures manuscript shows that title exactly once, not twice;
* an end-block float is GUARDED by ``\ifcsname scitexfigplaced@<n>``, so a figure
  placed inline with ``\scitexfig{<n>}`` is not also duplicated at the end.

Image paths are named relative to the project root (``./01_manuscript/...``,
:func:`scitex_writer._utils._tex_paths.tex_path`) when the caller passes
``tex_root``, never by the absolute path of the checkout: the flattened
manuscript that inlines ``FINAL.tex`` is a tracked file, and an absolute path
there names whichever checkout compiled last. The compile runs from the project
root, the base every ``./``-prefixed ``\input`` already resolves from.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple, Union

from ..._utils._caption_footnote import split_caption_footnote
from ..._utils._tex_paths import tex_path
from ._figures_media import figure_number, mains, numbered

HEADER_NAME = "00_Figures_Header.tex"
ENABLED_MARKER = ".figures_enabled"
DEFAULT_MAX_HEIGHT_FRAC = "0.78"
FIGURE_WIDTH = r"0.9\textwidth"

# Comment-only fallback: NO renderable float, caption or label (see module doc).
FALLBACK_HEADER = r"""%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% FIGURES
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% No figures are present in this manuscript.
%% The "Figures" \section*, \label{figures}, \pdfbookmark and \clearpage are
%% emitted once by base.tex (single source of truth). This fallback header
%% deliberately emits NO heading and NO figure float, so an empty-figures
%% manuscript shows the "Figures" title exactly once instead of twice.
%%
%% To add a figure: place an image in caption_and_media/ named XX_description.png,
%% add a matching caption XX_description.tex, then reference it in the body as
%% Figure~\ref{fig:XX_description}.
"""


def compile_legends(caption_media_dir: Path, compiled_dir: Path) -> int:
    """Derive ``compiled_dir/NN_*.tex`` from each MAIN caption body.

    The caption is copied with its comment lines stripped (the ``%% Edit this
    file:`` hint must never leak into the PDF) under a metadata banner. Panels are
    excluded: they carry no caption and get no compiled float of their own.
    """
    compiled = 0
    for caption_file in mains(caption_media_dir, ".tex"):
        figure_id = caption_file.stem
        body = "\n".join(
            line
            for line in caption_file.read_text(encoding="utf-8").splitlines()
            if not line.startswith("%")
        )
        (compiled_dir / f"{figure_id}.tex").write_text(
            f"% FIGURE METADATA - Figure ID {figure_id}, "
            f"Number {figure_number(figure_id)}\n"
            "% FIGURE TYPE: Image\n"
            "% Included by compile_figure_tex_files(); not a standalone document.\n"
            f"{body}\n",
            encoding="utf-8",
        )
        compiled += 1
    return compiled


def handle_figure_visibility(jpg_dir: Path, compiled_dir: Path, no_figs: bool) -> bool:
    """Write (or clear) the ``.figures_enabled`` marker; return its new state."""
    marker = compiled_dir / ENABLED_MARKER
    enabled = not no_figs and any(jpg_dir.glob("*.jpg"))
    if enabled:
        marker.write_text("% Figures enabled\n", encoding="utf-8")
    elif marker.exists():
        marker.unlink()
    return enabled


def read_caption(caption_file: Path, number: str) -> Tuple[str, Optional[str], str]:
    r"""Return ``(caption, footnote, title)`` for one figure's caption file.

    Comment and blank lines are dropped; an author-declared
    ``\captionfootnote{...}`` is split out (a ``\footnote`` inside a float does not
    render); the ``\textbf{...}`` title is lifted for the PDF bookmark. A missing
    or comment-only caption falls back to a generated one -- a figure without a
    caption must still typeset.
    """
    fallback = (
        f"\\caption{{\\textbf{{Figure {number}}}\\\\Description for figure {number}.}}"
    )
    if not (caption_file.exists() or caption_file.is_symlink()):
        return fallback, None, ""
    caption = "\n".join(
        line
        for line in caption_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("%")
    )
    if not caption:
        return fallback, None, ""

    caption, footnote = split_caption_footnote(caption)
    title = ""
    marker = "\\textbf{"
    start = caption.find(marker)
    if start != -1:
        end = caption.find("}", start + len(marker))
        if end != -1:
            title = caption[start + len(marker) : end].strip().rstrip(".")
    return caption, footnote, title


def figure_float(
    number: str,
    figure_id: str,
    image_path: Union[Path, str],
    caption: str,
    footnote: Optional[str],
    title: str,
    max_height: str,
) -> List[str]:
    r"""The complete ``figure*`` float for one figure, as lines.

    ``[htbp]`` lets LaTeX place it at a nearby page top/bottom. The height is
    capped at ``max_height`` so a tall figure cannot push its caption off the page.
    """
    bookmark = f"Figure {number} --- {title}" if title else f"Figure {number}"
    lines = [
        f"% Figure {number}",
        "\\begin{figure*}[htbp]",
        f"    \\pdfbookmark[2]{{{bookmark}}}{{.{number}}}",
        "    \\centering",
        f"    \\includegraphics[width={FIGURE_WIDTH},totalheight={max_height},"
        f"keepaspectratio]{{{image_path}}}",
        f"    {caption}",
    ]
    # A label the author already wrote is never duplicated.
    if "\\label{fig:" not in caption:
        lines.append(f"    \\label{{fig:{figure_id}}}")
    lines.append("\\end{figure*}")
    # \footnotetext goes AFTER the float closes. Kept in the placeable file so it
    # travels with the float in BOTH placement modes (inline \scitexfig{<n>} and
    # the guarded end-of-document block).
    if footnote:
        lines.append(f"\\footnotetext{{{footnote}}}")
    return lines


def compile_figure_tex_files(
    caption_media_dir: Path,
    jpg_dir: Path,
    compiled_dir: Path,
    compiled_file: Path,
    max_height_frac: str = DEFAULT_MAX_HEIGHT_FRAC,
    tex_root: Optional[Path] = None,
) -> dict:
    r"""Assemble ``FINAL.tex`` from the compiled figures.

    With NO real figure, writes the comment-only ``00_Figures_Header.tex`` fallback
    (no float). With real figures, writes each float into ``_placeable/<number>.tex``
    (so the author may place it inline with ``\scitexfig{<number>}``) and emits a
    GUARDED copy into ``FINAL.tex`` so an inline-placed figure is not duplicated.

    An image is looked up as ``<figure_id>.jpg`` first, then ``<number>.jpg`` --
    the latter is the composite a panelled figure's panels were tiled into.

    ``tex_root`` is the project root: the ``\includegraphics`` path is written
    relative to it (``None`` keeps the path as given).

    Returns ``{"figure_count", "fallback_header", "figures"}``.
    """
    max_height = f"{max_height_frac}\\textheight"
    real_figures = [p for p in numbered(compiled_dir, ".tex") if p.name != HEADER_NAME]

    lines = [
        "% Generated by compile_figure_tex_files()",
        "% This file includes all figure files in order",
        "",
    ]
    compiled_file.parent.mkdir(parents=True, exist_ok=True)

    if not real_figures:
        (compiled_dir / HEADER_NAME).write_text(FALLBACK_HEADER, encoding="utf-8")
        lines.append(FALLBACK_HEADER)
        compiled_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"figure_count": 0, "fallback_header": True, "figures": []}

    placeable_dir = compiled_dir / "_placeable"
    placeable_dir.mkdir(parents=True, exist_ok=True)

    figures = []
    for compiled_tex in real_figures:
        figure_id = compiled_tex.stem
        number = figure_number(figure_id)
        caption, footnote, title = read_caption(
            caption_media_dir / f"{figure_id}.tex", number
        )

        image_path = jpg_dir / f"{figure_id}.jpg"
        if not image_path.exists():
            image_path = jpg_dir / f"{number}.jpg"

        float_lines = figure_float(
            number,
            figure_id,
            tex_path(image_path, tex_root),
            caption,
            footnote,
            title,
            max_height,
        )
        placeable_file = placeable_dir / f"{number}.tex"
        placeable_file.write_text("\n".join(float_lines) + "\n", encoding="utf-8")

        lines.append(f"\\ifcsname scitexfigplaced@{number}\\endcsname\\else")
        lines += float_lines
        lines.append("\\fi")
        lines.append("")

        figures.append(
            {
                "name": figure_id,
                "number": number,
                "image": str(image_path),
                "tex": str(compiled_tex),
                "placeable": str(placeable_file),
                "has_footnote": footnote is not None,
            }
        )

    compiled_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "figure_count": len(real_figures),
        "fallback_header": False,
        "figures": figures,
    }


__all__ = [
    "DEFAULT_MAX_HEIGHT_FRAC",
    "ENABLED_MARKER",
    "FALLBACK_HEADER",
    "HEADER_NAME",
    "compile_figure_tex_files",
    "compile_legends",
    "figure_float",
    "handle_figure_visibility",
    "read_caption",
]

# EOF

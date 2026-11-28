#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_figures_pipeline.py

r"""The figure pipeline: a pure-Python port of ``process_figures.sh``.

Ports the shell module (plus every ``.src`` under ``process_figures_modules/``)
stage for stage, reading the SAME config keys the shell read via ``yq``:
``figures.dir``, ``figures.caption_media_dir``, ``figures.jpg_dir``,
``figures.compiled_dir``, ``figures.compiled_file`` and the optional
``figures.max_height_frac`` from ``config/config_<doc_type>.yaml``.

This module is the ORCHESTRATOR: it resolves and boundary-checks the configured
paths, then runs the media stages (:mod:`._figures_media`) followed by the LaTeX
stages (:mod:`._figures_tex`) in the shell's order --

    init -> lowercase panel ids -> drop panel captions -> ensure captions
         -> convert cascade -> compose panels -> link JPGs -> placeholders
         -> [crop] -> compile legends -> visibility marker -> assemble FINAL.tex

Three shell behaviours this port deliberately CHANGES. Each replaced a SILENT
degradation, never a working path:

* ONE image backend (Pillow, :mod:`scitex_writer._utils._figure_image`) instead of
  the ``magick``/``convert``/``mogrify``/``montage`` cascade, every rung of which
  fell through silently when its binary was absent -- crop became a no-op and
  tiling ``cp``-ed the first panel and called it a composite;
* panels are really TILED into their composite. The shell's
  ``copy_composed_jpg_files`` ``cp``-ed panel *a* to ``NN.jpg`` "for now", and its
  ``auto_tile_panels`` scanned ``jpg_for_compilation`` -- which by construction
  never holds panels, because the linking step skips them -- so the montage path
  was dead code and every panelled figure shipped as its first panel;
* an absent converter (``libreoffice`` for PPTX, ``mmdc`` for Mermaid) FAILS LOUD
  with an install hint when such a source is actually present, instead of warning
  and leaving the figure's ``.jpg`` missing -- which breaks ``\includegraphics``
  much later with an error pointing nowhere near the real cause.

Robust by construction: pathlib only (never shells out to find/rm/mv); every write
target is resolved and asserted to live INSIDE the project root; fail-loud
(explicit error dict + actionable hint) on a missing project dir / config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..._dataclasses import FiguresResult
from ..utils import resolve_project_path
from ._figures_media import (
    cleanup_panel_captions,
    compose_panels,
    convert_formats,
    create_placeholders,
    crop_compilation_jpgs,
    ensure_caption,
    ensure_lower_letter_id,
    init_figures,
    link_compilation_jpgs,
)
from ._figures_tex import (
    DEFAULT_MAX_HEIGHT_FRAC,
    compile_figure_tex_files,
    compile_legends,
    handle_figure_visibility,
)

DOC_DIRS = {
    "manuscript": "01_manuscript",
    "supplementary": "02_supplementary",
    "revision": "03_revision",
}

_CFG_KEYS = {
    "figure_dir": ("figures", "dir"),
    "caption_media_dir": ("figures", "caption_media_dir"),
    "jpg_dir": ("figures", "jpg_dir"),
    "compiled_dir": ("figures", "compiled_dir"),
    "compiled_file": ("figures", "compiled_file"),
}


def _cfg_get(cfg: dict, path, default=None):
    """Nested dict lookup by a key-tuple; ``default`` if any level is absent."""
    cur = cfg
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _resolve(project_path: Path, rel) -> Optional[Path]:
    """Resolve a config path (possibly ``./``-relative) against the project root."""
    if not rel:
        return None
    rel = str(rel)
    if rel.startswith("./"):
        rel = rel[2:]
    return (project_path / rel).resolve()


def _within(boundary: Path, target: Path) -> bool:
    """True iff ``target`` resolves to a path inside ``boundary`` (guard ``..``)."""
    try:
        target.resolve().relative_to(boundary)
        return True
    except ValueError:
        return False


def _load_config(project_path: Path, doc_type: str):
    """Return ``(cfg, error)`` for the doc type's config file."""
    config_path = project_path / "config" / f"config_{doc_type}.yaml"
    if not config_path.exists():
        return None, (
            f"Config not found: {config_path}. "
            f"Run `scitex-writer update-project` or check --doc-type."
        )
    try:
        import yaml
    except ImportError:
        return None, "PyYAML not installed. Fix: pip install pyyaml"
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}, None
    except yaml.YAMLError as e:
        return None, f"{config_path} is not valid YAML: {e}"


def resolve_paths(project_path: Path, cfg: dict):
    """Return ``(paths, error)``: every configured figure path, boundary-checked."""
    paths = {}
    for name, key in _CFG_KEYS.items():
        resolved = _resolve(project_path, _cfg_get(cfg, key))
        if resolved is None:
            return None, (
                f"{'.'.join(key)} is missing in the config; cannot resolve the "
                f"figure {name.replace('_', ' ')}."
            )
        paths[name] = resolved

    boundary = project_path.resolve()
    if not all(_within(boundary, p) for p in paths.values()):
        return None, (
            "Refusing to run: a figures.* path resolves OUTSIDE the project root "
            f"{boundary} (config path escape via '..'?)."
        )
    return paths, None


def max_height_frac(cfg: dict) -> str:
    """The configured figure height cap; the default for an unset / yq-null key."""
    frac = _cfg_get(cfg, ("figures", "max_height_frac"))
    if frac in (None, "", "null"):
        return DEFAULT_MAX_HEIGHT_FRAC
    return str(frac)


def process(
    project_dir: str,
    doc_type: str = "manuscript",
    no_figs: bool = False,
    pptx: bool = False,
    crop: bool = False,
) -> dict:
    """Run the whole figure pipeline for ``doc_type`` and return its outcome.

    Parameters
    ----------
    project_dir : str
        Path to the scitex-writer project directory.
    doc_type : str
        One of 'manuscript' (default), 'supplementary', 'revision'.
    no_figs : bool
        Skip all IMAGE work (the shell's ``no_figs``): captions are still tidied
        and the compiled tree is still assembled, but nothing is converted,
        composed, linked or placeheld, and figures are DISABLED.
    pptx : bool
        Also convert ``NN_*.pptx`` slides through LibreOffice (the shell's ``p2t``).
        Off by default -- it is slow and needs LibreOffice on PATH.
    crop : bool
        Trim the uniform border off each compilation JPG (the shell's ``--crop``).

    Returns
    -------
    dict
        The serialized :class:`FiguresResult`. On failure ``error`` carries an
        actionable hint (fail-loud, never a silent no-op).
    """
    try:
        if doc_type not in DOC_DIRS:
            return {
                "success": False,
                "error": (
                    f"Invalid doc_type '{doc_type}'. Must be one of: {tuple(DOC_DIRS)}"
                ),
            }

        project_path = resolve_project_path(project_dir)
        if not project_path.is_dir():
            return {
                "success": False,
                "error": (
                    f"Project directory not found: {project_path}. "
                    f"Check the path passed as project_dir."
                ),
            }

        cfg, error = _load_config(project_path, doc_type)
        if error:
            return {"success": False, "error": error}
        paths, error = resolve_paths(project_path, cfg)
        if error:
            return {"success": False, "error": error}

        boundary = project_path.resolve()
        caption_media_dir = paths["caption_media_dir"]
        jpg_dir = paths["jpg_dir"]
        compiled_dir = paths["compiled_dir"]

        warnings = init_figures(
            paths["figure_dir"], caption_media_dir, jpg_dir, compiled_dir
        )
        renamed = ensure_lower_letter_id(caption_media_dir)
        panel_captions_removed = cleanup_panel_captions(caption_media_dir)
        captions_created = ensure_caption(caption_media_dir, boundary)

        converted = composed = placeholders = cropped = 0
        if not no_figs:
            converted = convert_formats(caption_media_dir, pptx)
            composed = compose_panels(caption_media_dir)
            warnings += link_compilation_jpgs(caption_media_dir, jpg_dir)
            placeholders = create_placeholders(caption_media_dir, jpg_dir)
            if crop:
                cropped = crop_compilation_jpgs(jpg_dir)

        compile_legends(caption_media_dir, compiled_dir)
        enabled = handle_figure_visibility(jpg_dir, compiled_dir, no_figs)
        gathered = compile_figure_tex_files(
            caption_media_dir,
            jpg_dir,
            compiled_dir,
            paths["compiled_file"],
            max_height_frac(cfg),
            tex_root=boundary,
        )

        result = FiguresResult(
            success=True,
            figures_compiled=gathered["figure_count"],
            captions_created=captions_created,
            panel_captions_removed=panel_captions_removed,
            renamed_panels=renamed,
            converted=converted,
            composed=composed,
            placeholders_created=placeholders,
            cropped=cropped,
            figures=gathered["figures"],
            compiled_file=str(paths["compiled_file"]),
            figures_enabled=enabled,
            fallback_header=gathered["fallback_header"],
            skipped=no_figs,
            warnings=warnings,
        )
        result.validate()
        return result.to_dict()
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


__all__ = ["DOC_DIRS", "max_height_frac", "process", "resolve_paths"]

# EOF

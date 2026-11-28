#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_tables_pipeline.py

r"""The table pipeline: a pure-Python port of ``process_tables.sh``.

Ports the shell module (plus its sourced ``03_csv2tex.src`` / ``04_gather.src``)
stage for stage, reading the SAME config keys the shell read via ``yq``:
``tables.dir``, ``tables.caption_media_dir``, ``tables.compiled_dir`` and
``tables.compiled_file`` from ``config/config_<doc_type>.yaml``.

Stages (``process`` runs them in order):

1. ``init_tables``       -- clear ``compiled_dir/*.tex``, create the table dirs,
                            truncate the gathered ``FINAL.tex``.
2. ``xlsx2csv_convert``  -- refresh ``NN_*.csv`` from a newer ``NN_*.xlsx/.xls``.
3. ``ensure_caption``    -- write a default ``NN_*.tex`` caption where none exists.
4. ``csv2tex``           -- render each ``NN_*.csv`` through the ONE pandas
                            backend (:mod:`scitex_writer._utils._csv_table`).
5. ``gather_table_tex_files`` -- assemble ``FINAL.tex`` (+ ``_placeable/`` copies).

Two behaviours the shell pinned and this port keeps:

* the NO-tables fallback header emits **no table float** -- only LaTeX comments
  (card writer-stray-table-zero-artifact: a placeholder float rendered as a
  stray counter-numbered "Table 0" with a spurious ``tab:0_Tables_Header``
  label);
* an end-block ``\input`` is GUARDED by ``\ifcsname scitextabplaced@<n>``, so a
  table placed inline with ``\scitextab{<n>}`` is not also duplicated at the end.

Robust by construction: pathlib only (never shells out to find/rm/mv); every
write target is resolved and asserted to live INSIDE the project root; fail-loud
(explicit error dict + actionable hint) on a missing project dir / config.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..._dataclasses import TablesResult
from ..._utils._csv_table import MAX_ROWS, render_csv_table
from ..._utils._tex_paths import tex_path
from ..utils import resolve_project_path

DOC_DIRS = {
    "manuscript": "01_manuscript",
    "supplementary": "02_supplementary",
    "revision": "03_revision",
}

_CFG_KEYS = {
    "table_dir": ("tables", "dir"),
    "caption_media_dir": ("tables", "caption_media_dir"),
    "compiled_dir": ("tables", "compiled_dir"),
    "compiled_file": ("tables", "compiled_file"),
}

HEADER_NAME = "00_Tables_Header.tex"

# Comment-only fallback: NO renderable float, caption or label (see module doc).
FALLBACK_HEADER = r"""%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% TABLES
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% No tables are present in this manuscript.
%% The "Tables" \section*, \label{tables} and \pdfbookmark are emitted once by
%% base.tex (single source of truth). This fallback header deliberately emits
%% NO table float, caption or label, so an empty-tables manuscript never shows
%% a stray placeholder "Table" (previously \label{tab:0_Tables_Header}).
%%
%% To add a table: place a CSV in caption_and_media/ named XX_description.csv,
%% add a matching caption XX_description.tex, then reference it in the body as
%% Table~\ref{tab:XX_description}.
"""


def _default_caption(rel_path: str) -> str:
    """The placeholder caption written for a CSV that has none (shell parity)."""
    return (
        f"%% Edit this file: {rel_path}\n"
        "\\caption{\\textbf{TABLE TITLE HERE}\\\\\n"
        "\\smallskip\n"
        f"TABLE CAPTION HERE. Edit this caption at \\url{{{rel_path}}}.\n"
        "}\n"
    )


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


def _numbered(directory: Path, suffix: str):
    """Sorted ``NN*<suffix>`` entries of ``directory`` (the shell's ``[0-9]*`` glob)."""
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob(f"[0-9]*{suffix}") if p.is_file())


def init_tables(
    table_dir: Path, caption_media_dir: Path, compiled_dir: Path, compiled_file: Path
) -> None:
    """Stage 1: clear stale compiled tables and (re)create the table directories."""
    if compiled_dir.is_dir():
        for stale in compiled_dir.glob("*.tex"):
            stale.unlink()
    for directory in (table_dir, caption_media_dir, compiled_dir):
        directory.mkdir(parents=True, exist_ok=True)
    compiled_file.parent.mkdir(parents=True, exist_ok=True)
    compiled_file.write_text("\n", encoding="utf-8")


def xlsx_to_csv(xlsx_file: Path, csv_file: Path) -> None:
    """Convert one Excel file to CSV: pandas first, else the ``xlsx2csv`` binary.

    Raises the underlying error when neither route works -- a table silently
    missing from the PDF is worse than a loud failure.
    """
    try:
        import pandas as pd

        pd.read_excel(xlsx_file).to_csv(csv_file, index=False)
        return
    except Exception:
        binary = shutil.which("xlsx2csv")
        if binary is None:
            raise
        subprocess.run(
            [binary, str(xlsx_file), str(csv_file)],
            capture_output=True,
            text=True,
            check=True,
        )


def xlsx2csv_convert(caption_media_dir: Path) -> int:
    """Stage 2: refresh each ``NN_*.csv`` whose Excel source is newer (or absent).

    Returns the number of files converted.
    """
    converted = 0
    excels = _numbered(caption_media_dir, ".xlsx") + _numbered(
        caption_media_dir, ".xls"
    )
    for xlsx_file in sorted(excels):
        csv_file = xlsx_file.with_suffix(".csv")
        if csv_file.exists() and csv_file.stat().st_mtime >= xlsx_file.stat().st_mtime:
            continue
        xlsx_to_csv(xlsx_file, csv_file)
        converted += 1
    return converted


def ensure_caption(caption_media_dir: Path, project_path: Path) -> int:
    """Stage 3: write a default caption for every CSV lacking one.

    A symlinked caption counts as present (the shell tested ``-f || -L``).
    Returns the number of caption files created.
    """
    created = 0
    for csv_file in _numbered(caption_media_dir, ".csv"):
        caption_file = csv_file.with_suffix(".tex")
        if caption_file.exists() or caption_file.is_symlink():
            continue
        try:
            rel_path = str(caption_file.resolve().relative_to(project_path))
        except ValueError:
            rel_path = caption_file.name
        caption_file.write_text(_default_caption(rel_path), encoding="utf-8")
        created += 1
    return created


def csv2tex(
    caption_media_dir: Path, compiled_dir: Path, max_rows: int = MAX_ROWS
) -> list:
    """Stage 4: render every ``NN_*.csv`` to ``compiled_dir/NN_*.tex``.

    ONE backend (pandas) -- see :mod:`scitex_writer._utils._csv_table` for why the
    shell's 4-way backend selection is gone. Returns one dict per table.
    """
    rendered = []
    for csv_file in _numbered(caption_media_dir, ".csv"):
        caption_file = csv_file.with_suffix(".tex")
        has_caption = caption_file.exists() or caption_file.is_symlink()
        caption = (
            caption_file.read_text(encoding="utf-8").strip() if has_caption else None
        )
        compiled_file = compiled_dir / f"{csv_file.stem}.tex"
        latex = render_csv_table(csv_file, caption=caption, max_rows=max_rows)
        compiled_file.write_text(latex + "\n", encoding="utf-8")

        import pandas as pd

        frame = pd.read_csv(csv_file)
        rendered.append(
            {
                "name": csv_file.stem,
                "csv": str(csv_file),
                "tex": str(compiled_file),
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "truncated": bool(len(frame) > max_rows),
                "caption_generated": not has_caption,
            }
        )
    return rendered


def gather_table_tex_files(
    compiled_dir: Path, compiled_file: Path, tex_root: Optional[Path] = None
) -> dict:
    """Stage 5: assemble ``FINAL.tex`` from the compiled tables.

    With NO real table, writes the comment-only ``00_Tables_Header.tex`` fallback
    (no float -- card writer-stray-table-zero-artifact) and inputs it. With real
    tables, copies each into ``_placeable/<number>.tex`` (so the author may place
    it inline with ``\\scitextab{<number>}``) and emits a GUARDED end-block
    ``\\input`` so an inline-placed table is not duplicated.

    ``tex_root`` is the project root: each ``\\input`` names its file relative
    to it (:func:`scitex_writer._utils._tex_paths.tex_path`; ``None`` keeps the
    path as given), so the flattened manuscript never carries the checkout's
    absolute path.

    Returns ``{"table_count": int, "fallback_header": bool}``.
    """
    real_tables = [p for p in _numbered(compiled_dir, ".tex") if p.name != HEADER_NAME]
    has_real_tables = bool(real_tables)

    lines = [
        "% Auto-generated file containing all table inputs",
        "% Generated by gather_table_tex_files()",
        "",
    ]

    if not has_real_tables:
        header_file = compiled_dir / HEADER_NAME
        header_file.write_text(FALLBACK_HEADER, encoding="utf-8")
        lines.append(f"\\input{{{tex_path(header_file, tex_root)}}}")
        lines.append("")
        compiled_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"table_count": 0, "fallback_header": True}

    placeable_dir = compiled_dir / "_placeable"
    placeable_dir.mkdir(parents=True, exist_ok=True)
    for table_tex in real_tables:
        number = table_tex.stem.split("_", 1)[0]
        shutil.copyfile(table_tex, placeable_dir / f"{number}.tex")
        lines.append(f"% Table from: {table_tex.name}")
        lines.append(
            f"\\ifcsname scitextabplaced@{number}\\endcsname"
            f"\\else\\input{{{tex_path(table_tex, tex_root)}}}\\fi"
        )
        lines.append("")
    compiled_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"table_count": len(real_tables), "fallback_header": False}


def process(
    project_dir: str,
    doc_type: str = "manuscript",
    no_tables: bool = False,
    max_rows: int = MAX_ROWS,
) -> dict:
    """Run the whole table pipeline for ``doc_type`` and return its outcome.

    Parameters
    ----------
    project_dir : str
        Path to the scitex-writer project directory.
    doc_type : str
        One of 'manuscript' (default), 'supplementary', 'revision'.
    no_tables : bool
        Skip all table processing (the shell's ``--no_tables`` early exit).
    max_rows : int
        Data rows shown per table before truncation.

    Returns
    -------
    dict
        The serialized :class:`TablesResult`. On failure ``error`` carries an
        actionable hint (fail-loud, never a silent no-op).
    """
    try:
        if no_tables:
            return TablesResult(success=True, skipped=True).to_dict()

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

        config_path = project_path / "config" / f"config_{doc_type}.yaml"
        if not config_path.exists():
            return {
                "success": False,
                "error": (
                    f"Config not found: {config_path}. "
                    f"Run `scitex-writer update-project` or check --doc-type."
                ),
            }
        try:
            import yaml
        except ImportError:
            return {
                "success": False,
                "error": "PyYAML not installed. Fix: pip install pyyaml",
            }
        try:
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            return {"success": False, "error": f"{config_path} is not valid YAML: {e}"}

        paths = {}
        for name, key in _CFG_KEYS.items():
            resolved = _resolve(project_path, _cfg_get(cfg, key))
            if resolved is None:
                return {
                    "success": False,
                    "error": (
                        f"{'.'.join(key)} is missing in {config_path}; "
                        f"cannot resolve the table {name.replace('_', ' ')}."
                    ),
                }
            paths[name] = resolved

        boundary = project_path.resolve()
        if not all(_within(boundary, p) for p in paths.values()):
            return {
                "success": False,
                "error": (
                    "Refusing to run: a tables.* path resolves OUTSIDE the "
                    f"project root {boundary} (config path escape via '..'?)."
                ),
            }

        init_tables(
            paths["table_dir"],
            paths["caption_media_dir"],
            paths["compiled_dir"],
            paths["compiled_file"],
        )
        xlsx_converted = xlsx2csv_convert(paths["caption_media_dir"])
        captions_created = ensure_caption(paths["caption_media_dir"], boundary)
        tables = csv2tex(
            paths["caption_media_dir"], paths["compiled_dir"], max_rows=max_rows
        )
        gathered = gather_table_tex_files(
            paths["compiled_dir"], paths["compiled_file"], tex_root=boundary
        )

        result = TablesResult(
            success=True,
            tables_compiled=gathered["table_count"],
            captions_created=captions_created,
            xlsx_converted=xlsx_converted,
            tables=tables,
            compiled_file=str(paths["compiled_file"]),
            fallback_header=gathered["fallback_header"],
        )
        result.validate()
        return result.to_dict()
    except Exception as e:
        return {"success": False, "error": str(e)}


__all__ = [
    "csv2tex",
    "ensure_caption",
    "gather_table_tex_files",
    "init_tables",
    "process",
    "xlsx2csv_convert",
    "xlsx_to_csv",
]

# EOF

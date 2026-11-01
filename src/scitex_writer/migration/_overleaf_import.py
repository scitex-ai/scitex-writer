#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/migration/_overleaf_import.py

"""Import logic: Overleaf ZIP -> scitex-writer project."""

import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Optional

from ._parsing import (
    IMRAD_SECTIONS,
    classify_section,
    detect_main_tex,
    extract_metadata,
    find_bib_files,
    find_image_files,
    find_style_files,
    find_table_files,
    parse_inputs,
    read_tex,
    split_inline_sections,
    unique_dest,
)


def from_overleaf(
    zip_path: str,
    output_dir: Optional[str] = None,
    project_name: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
    clone_fn: Optional[Callable[..., bool]] = None,
) -> dict:
    """Import an Overleaf ZIP export into a new scitex-writer project.

    Parameters
    ----------
    zip_path : str
        Path to the Overleaf ZIP file.
    output_dir : str, optional
        Directory to create the project in. Defaults to ./<project_name>.
    project_name : str, optional
        Name for the new project. Derived from ZIP filename if omitted.
    dry_run : bool
        If True, analyze and report mapping without creating files.
    force : bool
        If True, overwrite output_dir if it already exists.
    clone_fn : callable, optional
        Function used to materialize the scitex-writer template skeleton at
        the output directory. Signature ``(project_dir: str, *,
        git_strategy: str) -> bool``. Defaults to
        :func:`scitex_writer._project._create.clone_writer_project` (which
        clones the template repo over the network). Tests inject a local
        skeleton-creator so the import runs fully offline.
    """
    try:
        zip_obj = Path(zip_path).resolve()
        if not zip_obj.exists():
            return {"success": False, "error": f"ZIP file not found: {zip_path}"}
        if not zipfile.is_zipfile(zip_obj):
            return {"success": False, "error": f"Not a valid ZIP file: {zip_path}"}

        if not project_name:
            project_name = zip_obj.stem
        out_path = (
            Path(output_dir).resolve() if output_dir else Path.cwd() / project_name
        )

        if out_path.exists() and not force:
            return {
                "success": False,
                "error": f"Output directory already exists: {out_path}\nUse --force to overwrite.",
            }

        tmp_dir = tempfile.mkdtemp(prefix="scitex_overleaf_import_")
        warnings = []

        try:
            # Resolve once: TMPDIR (hence mkdtemp output) may contain a
            # symlink (e.g. CI runners where tmp points at a scratch mount).
            # parse_inputs() resolves every \input path, so an unresolved
            # extraction root makes mapped paths lexically escape it and
            # _build_report()'s relative_to() raises ("not in the subpath
            # of ..."), failing the whole import. Normalising here keeps
            # rglob-derived and resolved paths under one lexical root.
            extracted = _extract_zip(zip_obj, Path(tmp_dir)).resolve()
            main_tex = detect_main_tex(extracted)
            if not main_tex:
                return {
                    "success": False,
                    "error": "No LaTeX file with \\documentclass found in the ZIP.",
                }

            main_content = read_tex(main_tex)
            inputs = parse_inputs(main_tex, extracted)
            metadata = extract_metadata(main_content)
            section_mapping, unmapped = _analyze_sections(
                inputs,
                extracted,
                main_content,
                main_tex,
                warnings,
            )
            bib_files = find_bib_files(extracted)
            image_files = [
                f
                for f in find_image_files(extracted)
                if f != main_tex.with_suffix(".pdf")
            ]
            table_files = find_table_files(extracted)
            style_files = find_style_files(extracted)

            report = _build_report(
                extracted,
                main_tex,
                section_mapping,
                metadata,
                bib_files,
                image_files,
                table_files,
                style_files,
                unmapped,
            )

            if dry_run:
                return {
                    "success": True,
                    "dry_run": True,
                    "project_path": str(out_path),
                    "mapping_report": report,
                    "warnings": warnings,
                    "message": f"Dry run: would create project at {out_path}",
                }

            _create_project(
                out_path,
                force,
                metadata,
                section_mapping,
                unmapped,
                bib_files,
                image_files,
                table_files,
                style_files,
                clone_fn=clone_fn,
            )

            n_mapped = sum(len(v) for v in section_mapping.values())
            if n_mapped == 0 and not unmapped:
                warnings.append(
                    "No IMRAD sections detected. Content may need manual arrangement."
                )

            return {
                "success": True,
                "dry_run": False,
                "project_path": str(out_path),
                "mapping_report": report,
                "warnings": warnings,
                "message": (
                    f"Imported {zip_obj.name} into {out_path}. "
                    f"Mapped {n_mapped} section(s), {len(bib_files)} bib, "
                    f"{len(image_files)} image(s), {len(table_files)} table(s)."
                ),
            }
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    except Exception as e:
        return {"success": False, "error": str(e)}


def _extract_zip(zip_obj: Path, tmp_path: Path) -> Path:
    """Extract ZIP and return the effective root directory."""
    with zipfile.ZipFile(zip_obj, "r") as zf:
        zf.extractall(tmp_path)
    top = list(tmp_path.iterdir())
    if len(top) == 1 and top[0].is_dir() and not list(tmp_path.glob("*.tex")):
        return top[0]
    return tmp_path


def _analyze_sections(inputs, extracted, main_content, main_tex, warnings):
    """Classify referenced .tex files into IMRAD sections."""
    mapping = {s: [] for s in IMRAD_SECTIONS}
    unmapped = []

    for entry in inputs:
        if not entry["exists"]:
            warnings.append(f"Referenced file not found: {entry['arg']}")
            continue
        p = entry["resolved_path"]
        if p.suffix != ".tex":
            continue
        content = read_tex(p)
        section = classify_section(p, content)
        if section:
            mapping[section].append((p, content))
        else:
            unmapped.append((p, content))

    if not any(mapping.values()) and not unmapped:
        for name, text in split_inline_sections(main_content).items():
            if name in mapping:
                mapping[name].append((main_tex, text))

        m = re.search(
            r"\\begin\{abstract\}(.*?)\\end\{abstract\}", main_content, re.DOTALL
        )
        if m and not mapping["abstract"]:
            mapping["abstract"].append((main_tex, m.group(1).strip()))

    return mapping, unmapped


def _build_report(
    extracted,
    main_tex,
    mapping,
    metadata,
    bib_files,
    image_files,
    table_files,
    style_files,
    unmapped,
):
    """Build a mapping report dict."""
    return {
        "main_tex": str(main_tex.relative_to(extracted)),
        "sections": {
            s: [str(p.relative_to(extracted)) for p, _ in files]
            for s, files in mapping.items()
            if files
        },
        "metadata": {
            "title": metadata["title"],
            "authors_found": metadata["authors_block"] is not None,
            "keywords_found": metadata["keywords"] is not None,
        },
        "bib_files": [str(f.relative_to(extracted)) for f in bib_files],
        "images": [str(f.relative_to(extracted)) for f in image_files],
        "tables": [str(f.relative_to(extracted)) for f in table_files],
        "custom_styles": [str(f.relative_to(extracted)) for f in style_files],
        "unmapped_tex": [str(p.relative_to(extracted)) for p, _ in unmapped],
    }


def _create_project(
    out_path,
    force,
    metadata,
    mapping,
    unmapped,
    bib_files,
    image_files,
    table_files,
    style_files,
    clone_fn: Optional[Callable[..., bool]] = None,
):
    """Create scitex-writer project and overlay Overleaf content."""
    if clone_fn is None:
        from .._project._create import clone_writer_project

        clone_fn = clone_writer_project

    if out_path.exists() and force:
        shutil.rmtree(out_path)

    if not clone_fn(str(out_path), git_strategy="none"):
        raise RuntimeError(f"Failed to clone scitex-writer template to {out_path}")

    shared = out_path / "00_shared"
    contents = out_path / "01_manuscript" / "contents"

    # Metadata
    if metadata["title"]:
        (shared / "title.tex").write_text(metadata["title"] + "\n", encoding="utf-8")
    if metadata["authors_block"]:
        (shared / "authors.tex").write_text(
            metadata["authors_block"] + "\n", encoding="utf-8"
        )
    if metadata["keywords"]:
        (shared / "keywords.tex").write_text(
            metadata["keywords"] + "\n", encoding="utf-8"
        )

    # IMRAD sections
    for name in IMRAD_SECTIONS:
        if not mapping[name]:
            continue
        combined = "\n\n".join(content for _, content in mapping[name])
        (contents / f"{name}.tex").write_text(combined + "\n", encoding="utf-8")

    # Unmapped tex
    for tex_path, content in unmapped:
        unique_dest(contents / tex_path.name).write_text(
            content + "\n", encoding="utf-8"
        )

    # Bibliography
    bib_dest = shared / "bib_files"
    bib_dest.mkdir(parents=True, exist_ok=True)
    for f in bib_files:
        shutil.copy2(f, unique_dest(bib_dest / f.name))

    # Images
    fig_dest = contents / "figures" / "caption_and_media"
    fig_dest.mkdir(parents=True, exist_ok=True)
    for f in image_files:
        shutil.copy2(f, unique_dest(fig_dest / f.name))

    # Tables
    tbl_dest = contents / "tables" / "caption_and_media"
    tbl_dest.mkdir(parents=True, exist_ok=True)
    for f in table_files:
        shutil.copy2(f, unique_dest(tbl_dest / f.name))

    # Custom styles
    if style_files:
        sty_dest = shared / "latex_styles"
        sty_dest.mkdir(parents=True, exist_ok=True)
        for f in style_files:
            shutil.copy2(f, unique_dest(sty_dest / f.name))


# EOF

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_utils/_tex_paths.py

r"""Paths as the generated ``.tex`` names them: relative to the project root.

The flattened ``manuscript.tex`` / ``supplementary.tex`` (and the figure and
table ``FINAL.tex`` files it inlines) are committed by most projects. An
absolute path in them names the checkout that last compiled -- a user's home
directory, a scratch disk, an agent's worktree -- so the tracked file changes
with the checkout and leaks where the authors keep their files.

The compile runs with the project root as its working directory (the shell
engines and :func:`compile_tex_structure.expand_inputs` already resolve
``./``-prefixed paths from there), so a ``./``-prefixed project-relative path
resolves the same way for every engine and in every checkout.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

__all__ = ["tex_path"]


def tex_path(path: Union[str, os.PathLike], root: Optional[Path]) -> str:
    """``path`` as a ``./``-prefixed POSIX path relative to ``root``.

    ``root`` is ``None`` (no project known) or ``path`` lies outside it: the
    path is returned unchanged -- a file outside the project has no portable
    name, and pretending otherwise would point at the wrong file.
    """
    p = Path(path)
    if root is None or not p.is_absolute():
        return str(path)
    root = Path(root)
    for base in dict.fromkeys((root, root.resolve())):
        for candidate in dict.fromkeys((p, p.resolve())):
            try:
                return "./" + candidate.relative_to(base).as_posix()
            except ValueError:
                continue
    return str(path)


# EOF

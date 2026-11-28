#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/_shown_path.py

"""A path as the flattened .tex may name it: never the checkout's absolute path.

The flattened manuscript.tex / supplementary.tex is tracked by most projects.
An absolute path in it (even in a comment) names whichever checkout compiled
last -- a home directory, a scratch disk, an agent worktree -- so the file
changes with the checkout and leaks where the authors keep their files.
"""

from pathlib import Path


def shown_path(path) -> str:
    """``path`` relative to the working directory (the project root the
    compile runs from), ``./``-prefixed, when it lies inside it; otherwise as
    given (a file outside the project has no portable name)."""
    p = Path(path)
    if not p.is_absolute():
        return str(path)
    try:
        return "./" + p.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


# EOF

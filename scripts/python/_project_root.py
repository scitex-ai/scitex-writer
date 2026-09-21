#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scripts/python/_project_root.py

"""Where the project root comes from, for the vendored scripts.

The name is ``SCITEX_WRITER_PROJECT_ROOT`` — the fleet convention is that every
writer setting is ``SCITEX_WRITER_<X>``. The unprefixed ``PROJECT_ROOT`` is
RETIRED, but these scripts are VENDORED into user workspaces, and a workspace
that exports the old name would otherwise get a compile that quietly used a
different root: a setting accepted and discarded, which is worse than either
failing or working. So the old name is still HONOURED for one migration cycle,
and never silently — reading it prints a warning that names its replacement.

Why the retired spelling is a CONSTANT and not written at the read sites: this
file ships in the wheel, and scitex-dev §6a scans shipped sources for
unprefixed ``os.environ`` reads. A literal at the read site would be a second
interface to keep alive; one constant is one place to delete when the cycle
ends, and the audit's allowlist entry for it is gone.

``environ`` is a parameter rather than a direct ``os.environ`` read in the
tests' path for the same reason ``_legacy_env`` takes one: the decision can be
tested against real dicts instead of a patched process environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Union

__all__ = ["ENV_PROJECT_ROOT", "RETIRED_PROJECT_ROOT", "resolve_project_root"]

ENV_PROJECT_ROOT = "SCITEX_WRITER_PROJECT_ROOT"
"""The namespaced name every writer setting uses now."""

RETIRED_PROJECT_ROOT = "PROJECT_ROOT"
"""The unprefixed name still honoured for one migration cycle."""


def resolve_project_root(
    default: Optional[Union[str, Path]] = None,
    environ: Optional[Mapping[str, Any]] = None,
) -> str:
    """Resolve the project root the vendored scripts should work in.

    Parameters
    ----------
    default : str or Path, optional
        Returned when neither variable is set. Defaults to the working
        directory, which is what the call sites used before.
    environ : Mapping[str, Any], optional
        The environment to read. Defaults to ``os.environ``.

    Returns
    -------
    str
        The resolved root, as text (what the call sites already passed around).

    Examples
    --------
    >>> resolve_project_root(environ={"SCITEX_WRITER_PROJECT_ROOT": "/tmp/p"})
    '/tmp/p'
    >>> resolve_project_root(default="/tmp/here", environ={})
    '/tmp/here'
    >>> resolve_project_root("/tmp/here", {"PROJECT_ROOT": "/tmp/old"})
    '/tmp/old'
    """
    env = os.environ if environ is None else environ
    namespaced = env.get(ENV_PROJECT_ROOT)
    if namespaced:
        return str(namespaced)
    retired = env.get(RETIRED_PROJECT_ROOT)
    if retired:
        print(
            f"WARNING: {RETIRED_PROJECT_ROOT} is retired — export "
            f"{ENV_PROJECT_ROOT} instead. The old name is still read for one "
            "migration cycle, and this workspace's compile keeps working.",
            file=sys.stderr,
        )
        return str(retired)
    return str(default) if default is not None else os.getcwd()


# EOF

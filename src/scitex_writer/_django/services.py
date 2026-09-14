#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project state service — creation, caching.

A `ProjectState` holds per-project editor state (compile status, log, dark mode)
that Flask previously kept on the `WriterEditor` instance. Cached in-process
with a TTL so repeated HTTP requests for the same project reuse the same state.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_project_cache: Dict[str, Tuple["ProjectState", float]] = {}
_CACHE_TTL_SECONDS = 3600


@dataclass
class ProjectState:
    """Per-project editor state (replaces Flask WriterEditor)."""

    project_dir: Path
    dark_mode: bool = False
    _compiling: bool = False
    _compile_result: Optional[Dict[str, Any]] = None
    _compile_log: str = ""
    _lock: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading

        self._lock = threading.Lock()


def get_or_create_project(project_dir: str) -> ProjectState:
    """Return a cached ProjectState for `project_dir`, creating one if missing.

    Raises FileNotFoundError if the directory does not exist.
    """
    _cleanup_expired()

    path = Path(project_dir).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Project directory not found: {path}")

    # The hub's leaf-v2 mount passes the PROJECT ROOT (?working_dir=<root>);
    # the legacy/standalone path may already pass the WORKSPACE. The leaf owns
    # root->workspace (scitex-hub contract 2026-09-14): resolve tolerantly so
    # state.project_dir is ALWAYS the workspace from here on. Every downstream
    # handler composes workspace-relative paths (compile.sh, 00_shared/, logs/,
    # PDFs) against state.project_dir, so resolving once here fixes them all at
    # the source. We do NOT scaffold here: the workspace must exist (the hub's
    # project-state init and the standalone CLI both ensure it); a bare empty
    # root raises the named NotAWriterWorkspaceError, consistent with the
    # _mcp compile entry (#389).
    from scitex_writer._ports.workspace import ensure_scholar_library_link
    from scitex_writer.workspace_layout import resolve_workspace

    workspace = resolve_workspace(path)

    key = str(workspace)
    if key in _project_cache:
        state, _ = _project_cache[key]
        _project_cache[key] = (state, time.time())
        return state

    state = ProjectState(project_dir=workspace)
    _project_cache[key] = (state, time.time())
    logger.info("[Writer] Created project state for %s", workspace)

    ensure_scholar_library_link(workspace)
    return state


def remove_project(project_dir: str) -> None:
    """Evict a project from the cache.

    Accepts either the PROJECT ROOT or the WORKSPACE and evicts the same key
    the load point caches under (the resolved workspace), so a root passed by
    the hub removes the state its compile created.
    """
    from scitex_writer.workspace_layout import resolve_workspace

    path = Path(project_dir).resolve()
    if not path.exists():
        _project_cache.pop(str(path), None)
        return
    try:
        workspace = resolve_workspace(path)
    except ValueError:
        workspace = path
    _project_cache.pop(str(workspace), None)
    _project_cache.pop(str(path), None)


def _cleanup_expired() -> None:
    now = time.time()
    expired = [
        k for k, (_, ts) in _project_cache.items() if now - ts > _CACHE_TTL_SECONDS
    ]
    for k in expired:
        _project_cache.pop(k, None)

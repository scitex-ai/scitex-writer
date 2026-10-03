#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_utils/_watch.py

"""
Watch mode for auto-recompilation.

Monitors file changes and triggers automatic recompilation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from scitex_logging import getLogger

logger = getLogger(__name__)


def watch_manuscript(
    project_dir: Path,
    interval: int = 2,
    on_compile: Optional[Callable] = None,
    timeout: Optional[int] = None,
    popen: Optional[Callable] = None,
) -> None:
    """
    Watch and auto-recompile manuscript on file changes.

    Args:
        project_dir: Path to writer project directory
        interval: Check interval in seconds
        on_compile: Callback function called after each compilation
        timeout: Optional timeout in seconds (None = infinite)
        popen: Process launcher with the same call shape as
            ``subprocess.Popen`` (cmd, cwd, stdout, stderr, text, bufsize).
            Defaults to :class:`subprocess.Popen`. Exposed so callers and
            tests can supply an alternate launcher without patching
            ``subprocess.Popen`` globally.

    Examples:
        >>> from pathlib import Path
        >>> def on_change():
        ...     print("Recompiled!")
        >>> watch_manuscript(Path("/path/to/project"), on_compile=on_change)
    """
    if popen is None:
        popen = subprocess.Popen

    # Get compile script from project directory
    compile_script = project_dir / "compile"

    if not compile_script.exists():
        logger.error(f"compile script not found: {compile_script}")
        return

    # Build watch command
    cmd = [str(compile_script), "-m", "-w"]

    logger.info(f"Starting watch mode for {project_dir}")
    logger.info("Press Ctrl+C to stop")

    process = None
    try:
        # Run watch script
        process = popen(
            cmd,
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line-buffered
        )

        # Stream output
        for line in iter(process.stdout.readline, ""):
            if line:
                sys.stdout.write(line.rstrip() + "\n")

                # Call callback on compilation events
                if on_compile and "Compilation" in line:
                    try:
                        on_compile()
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

        process.wait(timeout=timeout)

    except KeyboardInterrupt:
        logger.info("\nWatch mode stopped by user")
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    except Exception as e:
        logger.error(f"Watch mode error: {e}")
        if process:
            process.terminate()


__all__ = ["watch_manuscript"]

# EOF

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone local-dev launcher for the writer editor.

Delegates to `scitex_app._standalone.run_standalone`, which pre-wires
scitex-ui static assets + the workspace shell so the same local server
looks like scitex.ai/apps/writer.

Cloud deployments do NOT use this — they mount `scitex_writer._django.urls`
into their own Django project.
"""

from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path

from .._core._gui_runtime import DEFAULT_PORT
from ._legacy_env import raise_on_legacy_env



def contribute_allowed_host(host: str) -> list[str]:
    """Permit the address we are about to bind, and return the allow-list.

    BINDING TO AN ADDRESS IS THE STATEMENT THAT YOU INTEND TO BE REACHED ON IT.
    Requiring the caller to ALSO set an env var to permit what they just asked
    for is a trap, not a safeguard: Django answers 400 Bad Request to every
    request while the startup banner still prints a correct-looking URL, so it
    reads as a firewall problem. Reported by scitex-scholar 2026-08-23, who
    found the same hardcoded list in figrecipe, storage and scholar — a shared
    ancestor in the scitex-app SDK rather than four independent mistakes.

    APPENDED, NEVER ASSIGNED: an operator who set SCITEX_WRITER_ALLOWED_HOSTS
    keeps every entry they named. Returns the resulting list so callers (and
    tests) can see what was permitted rather than inferring it from the env.
    """
    allowed = [
        h.strip()
        for h in os.environ.get("SCITEX_WRITER_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    ]
    if host and host not in allowed:
        allowed.append(host)
    os.environ["SCITEX_WRITER_ALLOWED_HOSTS"] = ",".join(allowed)
    return allowed


def warn_if_wildcard_bind(host: str, allowed: list[str]) -> str | None:
    """Return a warning when 0.0.0.0 is bound with no reachable name allowed.

    0.0.0.0 MEANS "EVERY INTERFACE", WHICH NAMES NO HOST. Django matches the
    Host HEADER, so binding the wildcard address says nothing about the names
    callers will use, and allowing the literal "0.0.0.0" permits only that
    string. This is the one case the bind-implies-permission rule above cannot
    resolve, so it is stated with its remedy instead of being papered over with
    a wildcard — writer ships no authentication, and ALLOWED_HOSTS = ["*"]
    would make every reachable address an unauthenticated reader.
    """
    if host != "0.0.0.0" or len(allowed) > 1:
        return None
    return (
        "WARNING: bound to 0.0.0.0 (all interfaces) but no reachable hostname "
        "is allowed. Django matches the Host header, so requests arriving as "
        "anything other than localhost will be answered 400. Fix: "
        "SCITEX_WRITER_ALLOWED_HOSTS=<addr-or-name>[,<addr-or-name>] naming "
        "how callers will actually reach this machine."
    )

def run(
    project_dir: str,
    port: int = DEFAULT_PORT,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    desktop: bool = False,
    hot_reload: bool = False,
) -> None:
    """Launch the Django editor server locally on exactly ``port``.

    Uses `scitex_app.embed.run_standalone` (gets the full workspace shell
    from scitex-ui). When that import fails, names WHICH failure it was —
    scitex-app absent, or present but too old to expose `.embed` — and
    serves bare Django instead; every other error propagates.

    The requested port is bound as given: when it is already in use the
    server fails instead of drifting to the next free port (which used to
    leave a stack of duplicate instances behind).
    """
    project_path = Path(project_dir).resolve()
    if not project_path.exists():
        raise FileNotFoundError(f"Project directory not found: {project_path}")

    # A retired spelling exported by the caller's launcher is an error, not
    # something to quietly overwrite: it means they are configuring a writer
    # that stopped reading that name.
    raise_on_legacy_env()

    os.environ["SCITEX_WRITER_WORKING_DIR"] = str(project_path)
    os.environ["SCITEX_WORKING_DIR"] = str(project_path)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scitex_writer._django.settings")

    _allowed = contribute_allowed_host(host)
    _warning = warn_if_wildcard_bind(host, _allowed)
    if _warning:
        print(_warning)

    print(f"SciTeX Writer GUI: http://{host}:{port}")
    print(f"Project: {project_path}")
    print("Press Ctrl+C to stop")

    try:
        from scitex_app.embed import run_standalone
    except ImportError:
        from ._workspace_shell import REMEDY, probe_missing_shell

        run_standalone = None
        print(
            f"Note: {probe_missing_shell()}, so the workspace shell is "
            "unavailable; serving bare Django instead.\n"
            f"      Get it with: {REMEDY}"
        )

    import django

    django.setup()

    from django.core.management import call_command

    call_command("migrate", "--run-syncdb", verbosity=0)

    if run_standalone is not None:
        run_standalone(
            app_module="scitex_writer._django",
            port=port,
            host=host,
            open_browser=open_browser,
            hot_reload=hot_reload,
            working_dir=str(project_path),
            desktop=desktop,
        )
        return

    if open_browser and not desktop:
        threading.Timer(1.0, webbrowser.open, args=[f"http://{host}:{port}"]).start()

    noreload = [] if hot_reload else ["--noreload"]
    call_command("runserver", f"{host}:{port}", *noreload)

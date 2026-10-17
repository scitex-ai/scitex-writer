#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_cli/_completion.py

"""Shell tab-completion for the scitex-writer CLI.

Self-contained drop-in module (drop-in contract v1): ``install-shell-completion``
writes the click-generated completion script to the per-package drop-in file
``$SCITEX_DIR/writer/runtime/completion/scitex-writer`` (default
``~/.scitex/writer/runtime/completion/scitex-writer``) with an atomic rename,
skips the rewrite when the content is unchanged (idempotent), and prints the
drop-in path. It never touches shell startup files — sourcing the printed
path (or a loader that sources the drop-in directory) activates completion.

The script is generated IN-PROCESS via ``click.shell_completion`` from the
in-memory ``main_group`` object, so no ``scitex-writer`` console-script needs
to exist on ``$PATH`` (the CI / SIF failure mode of the old subprocess-based
shared helper). This module depends only on the stdlib and click — it must
never import scitex-dev (or anything else that could break ``--help``).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import click

PROG_NAME = "scitex-writer"

SHELLS = ["bash", "zsh", "fish"]


def _complete_var(prog_name: str) -> str:
    """Click's autocompletion env var: ``_<UPPER_PROG>_COMPLETE``."""
    return "_" + prog_name.upper().replace("-", "_") + "_COMPLETE"


def _generate_script(main_group: click.Group, shell: str, prog_name: str) -> str:
    """Return the click-generated completion script for ``shell`` in-process.

    Uses ``click.shell_completion.get_completion_class`` so no ``prog_name``
    console-script needs to exist on ``$PATH``.
    """
    from click.shell_completion import get_completion_class

    comp_cls = get_completion_class(shell)
    if comp_cls is None:  # pragma: no cover - SHELLS is constrained by Choice
        raise click.ClickException(f"Unsupported shell: {shell}")
    completer = comp_cls(main_group, {}, prog_name, _complete_var(prog_name))
    script = completer.source().strip()
    if not script:  # pragma: no cover - defensive; click always emits a body
        raise click.ClickException(
            f"Failed to generate {shell} completion script for {prog_name}."
        )
    return script


def _scitex_dir() -> Path:
    """Resolve ``$SCITEX_DIR`` (default ``~/.scitex``)."""
    return Path(os.environ.get("SCITEX_DIR", os.path.expanduser("~/.scitex")))


def _pkg_short(prog_name: str) -> str:
    """``scitex-writer`` -> ``writer`` (drop-in dir); others pass through."""
    if prog_name.startswith("scitex-"):
        return prog_name[len("scitex-") :]
    return prog_name


def _cache_path(prog_name: str) -> Path:
    """Drop-in file: ``$SCITEX_DIR/<short>/runtime/completion/<prog>``."""
    return _scitex_dir() / _pkg_short(prog_name) / "runtime" / "completion" / prog_name


def _write_atomic(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically (tmp file + rename)."""
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, 0o644)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def attach_shell_completion(main_group: click.Group, *, prog_name: str) -> None:
    """Register the four shell-completion leaves on ``main_group``."""

    @main_group.command("print-shell-completion")
    @click.option(
        "--shell",
        type=click.Choice(SHELLS),
        default="bash",
        help="Target shell. Default: bash.",
    )
    def print_shell_completion(shell: str) -> None:
        """Show the click-generated completion script on stdout.

        \b
        Example:
          $ scitex-writer print-shell-completion --shell bash
          $ scitex-writer print-shell-completion --shell zsh
          $ eval "$(scitex-writer print-shell-completion --shell bash)"
        """
        click.echo(_generate_script(main_group, shell, prog_name))

    @main_group.command("install-shell-completion")
    @click.option(
        "--shell",
        type=click.Choice(SHELLS),
        default="bash",
        help="Target shell. Default: bash.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Show the drop-in path without writing.",
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def install_shell_completion(shell: str, dry_run: bool, yes: bool) -> None:
        """Install the ``<TAB>``-completion drop-in file.

        \b
        Example:
          $ scitex-writer install-shell-completion
          $ scitex-writer install-shell-completion --shell zsh
          $ scitex-writer install-shell-completion --dry-run    # preview only

        \b
        Activate in the current shell after install:
          source ~/.scitex/writer/runtime/completion/scitex-writer
        """
        del yes  # accepted for §2 compliance; use --dry-run for preview
        drop_in = _cache_path(prog_name)

        if dry_run:
            click.echo(f"Would write completion drop-in to {drop_in}")
            return

        script = _generate_script(main_group, shell, prog_name) + "\n"
        drop_in.parent.mkdir(parents=True, exist_ok=True)

        try:
            existing = drop_in.read_text() if drop_in.is_file() else None
        except OSError:
            existing = None
        if existing == script:
            click.echo(f"Tab completion already installed at {drop_in}")
            return

        _write_atomic(drop_in, script)
        click.echo(f"Tab completion installed at {drop_in}")
        click.echo(f"Run: source {drop_in}")

    @main_group.command(
        "install-tab-completion",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def install_tab_completion_deprecated(ctx: click.Context) -> None:
        """(deprecated) Renamed to ``install-shell-completion``."""
        click.echo(
            f"error: `{prog_name} install-tab-completion` was renamed to "
            f"`{prog_name} install-shell-completion`.\n"
            f"Re-run with: {prog_name} install-shell-completion",
            err=True,
        )
        ctx.exit(2)

    @main_group.command(
        "completion",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def completion_deprecated(ctx: click.Context) -> None:
        """(deprecated) Renamed to ``install-shell-completion``."""
        click.echo(
            f"error: `{prog_name} completion` was renamed to "
            f"`{prog_name} install-shell-completion`.\n"
            f"Re-run with: {prog_name} install-shell-completion",
            err=True,
        )
        ctx.exit(2)


# EOF

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# Timestamp: "2025-11-12 14:19:14 (ywatanabe)"

r"""
Fast recursive TeX structure compiler.

Replaces \input{} commands with file contents in single pass.
Performance: O(n) instead of O(n²).
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional, Set

sys.path.insert(0, str(Path(__file__).parent))
from _build_id import (  # noqa: E402
    generate_build_id,
    inject_build_metadata,
    register_build,
)
from _shown_path import shown_path as _shown  # noqa: E402
from _signature_footer import (  # noqa: E402
    SIGNATURE_FOOTER_SENTINEL,
    build_footer_injection,
    resolve_signature_footer_enabled,
    resolve_writer_version,
)
from _tectonic_compat import apply_tectonic_compat  # noqa: E402
from _tex_signature import generate_signature  # noqa: E402
from _theme import read_config_theme as _read_config_theme  # noqa: E402,F401
from _theme import resolve_dark_mode as _resolve_dark_mode  # noqa: E402

# Unique marker for the inlined dark-mode block; also used as the idempotency
# sentinel so a repeated flatten does not stack a second copy.
DARK_MODE_SENTINEL = "% Dark mode styling (inlined at compile time)"

# The citation gate (banner mode) writes this artifact under the project root;
# when present it is injected right AFTER \begin{document} (before \maketitle)
# so a red "unverified citations" box lands at the top of page 1. Its first
# line is also the idempotency sentinel (a reflatten must not stack a copy).
CITATION_BANNER_ARTIFACT = ".scitex/writer/.citation_banner.tex"
CITATION_BANNER_SENTINEL = "scitex-writer citation banner"

# Idempotency sentinel for the auto-injected clew "Provenance marks" intro
# section (\clewIntro), placed near document start (after \end{frontmatter},
# else after \begin{document}) when the clew `intro` toggle is active.
CLEW_INTRO_SENTINEL = "% SciTeX clew intro section (inlined at compile time)"

# Line-anchored detectors for the clew presentation toggles that the flattened
# content carries (the toggles file is \input via packages.tex, so a
# \clewpres<name>true line lands in expanded_content when the toggle is on).
_CLEW_SIGNATURE_TOGGLE_RE = re.compile(r"(?m)^\s*\\clewpressignaturetrue\b")
_CLEW_INTRO_TOGGLE_RE = re.compile(r"(?m)^\s*\\clewpresintrotrue\b")


def _is_style_input(input_file: str) -> bool:
    r"""True if an \input target is a preamble style file (latex_styles/)."""
    return "latex_styles" in Path(input_file).parts


def _style_fallback(input_path: Path) -> Optional[Path]:
    r"""Resolve a latex_styles \input against 00_shared/latex_styles by basename.

    Preamble styles are \input via contents/latex_styles/ -- a dev-only,
    UNCOMMITTED symlink to 00_shared/latex_styles that a fresh clone/CI/worktree
    lacks. Resolved from cwd (= project root), like ./-prefixed inputs. Returns
    None if not a style input or the fallback is absent.
    """
    if "latex_styles" in input_path.parts:
        candidate = Path("00_shared") / "latex_styles" / input_path.name
        if candidate.exists():
            return candidate
    return None


def expand_inputs(
    file_path: Path,
    processed: Set[Path] = None,
    depth: int = 0,
    max_depth: int = 10,
    errors: Optional[list] = None,
) -> str:
    r"""
    Recursively expand \input{} commands.

    Args:
        file_path: TeX file to process
        processed: Set of already processed files (prevents infinite loops)
        depth: Current recursion depth
        max_depth: Maximum recursion depth
        errors: Accumulator for FATAL preamble-style misses (fail-loud). The
            top-level caller passes a list and aborts the compile if it is
            non-empty after expansion.

    Returns:
        Expanded content as string
    """
    if processed is None:
        processed = set()
    if errors is None:
        errors = []

    if depth > max_depth:
        return f"% ERROR: Max recursion depth ({max_depth}) exceeded\n"

    if not file_path.exists():
        return f"% SKIPPED: \\input{{{_shown(file_path)}}} (file not found)\n"

    # Prevent infinite loops
    file_path = file_path.resolve()
    if file_path in processed:
        return (
            f"% SKIPPED: \\input{{{_shown(file_path)}}} "
            "(already processed - circular reference)\n"
        )

    processed.add(file_path)

    # Read file
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"% ERROR: Could not read {_shown(file_path)}: {e}\n"

    # Find all \input{} commands (but not commented lines)
    lines = content.split("\n")
    result_lines = []

    for line in lines:
        # Skip commented lines
        if re.match(r"^\s*%", line):
            result_lines.append(line)
            continue

        # Check for \input{} command
        match = re.search(r"\\input\{([^}]+)\}", line)

        if match:
            input_file = match.group(1)

            # Add .tex if not present
            if not input_file.endswith(".tex"):
                input_file += ".tex"

            input_path = Path(input_file)

            # If relative path starting with ./, resolve from git root (current working directory)
            # Otherwise resolve relative to current file's directory
            if not input_path.is_absolute():
                if input_file.startswith("./"):
                    # Path like ./03_revision/... should be from git root
                    input_path = Path(input_file)
                else:
                    # Path like contents/... is relative to current file
                    input_path = file_path.parent / input_path

            # Fresh-checkout robustness: a latex_styles \input missing in
            # contents/ falls back to 00_shared/latex_styles (uncommitted dev
            # symlink -- see _style_fallback).
            if not input_path.exists():
                fb = _style_fallback(input_path)
                if fb is not None:
                    input_path = fb

            # Add header comment
            result_lines.append("")
            result_lines.append("% " + "=" * 70)
            result_lines.append(f"% File: {_shown(input_file)}")
            result_lines.append("% " + "=" * 70)

            if input_path.exists():
                expanded = expand_inputs(
                    input_path,
                    processed=processed,
                    depth=depth + 1,
                    max_depth=max_depth,
                    errors=errors,
                )
                result_lines.append(expanded)
            elif _is_style_input(input_file):
                # FAIL LOUD: a missing PREAMBLE STYLE input silently yields a
                # broken PDF (undefined \linenumbers etc.) on exit 0.
                msg = (
                    f"preamble style input not found: \\input{{{input_file}}} "
                    f"(searched contents/ and 00_shared/latex_styles/)"
                )
                errors.append(msg)
                result_lines.append(f"% FATAL: {msg}")
            else:
                result_lines.append(
                    f"% SKIPPED: \\input{{{input_file}}} (file not found)"
                )
            result_lines.append("")

        else:
            # No \input command, keep line as-is
            result_lines.append(line)

    return "\n".join(result_lines)


def compile_tex_structure(
    base_tex: Path,
    output_tex: Path,
    verbose: bool = True,
    dark_mode: bool = False,
    tectonic_mode: bool = False,
    signature_footer: bool = False,
) -> bool:
    r"""
    Compile TeX structure by expanding all \input{} commands.

    Args:
        base_tex: Base TeX file with \input commands
        output_tex: Output compiled TeX file
        verbose: Print progress
        dark_mode: Enable dark mode (black background, white text)
        tectonic_mode: Disable incompatible packages for tectonic engine
        signature_footer: Inject the opt-in visible footer (default OFF)

    Returns:
        True if successful
    """
    if not base_tex.exists():
        print(f"ERROR: Base file not found: {base_tex}")
        return False

    if verbose:
        print(f"Compiling TeX structure: {base_tex}")
        print(f"Output: {output_tex}")
        if dark_mode:
            print("Dark mode: enabled")
        if tectonic_mode:
            print("Tectonic mode: enabled (disabling incompatible packages)")

    # Generate per-compilation build ID (#77)
    build_id = generate_build_id()
    if verbose:
        print(f"Build ID: build:{build_id}")

    # Expand all inputs recursively. A missing PREAMBLE STYLE \input is FATAL
    # (would silently yield a broken PDF); collect any and abort below.
    style_errors: list = []
    expanded_content = expand_inputs(base_tex, errors=style_errors)
    if style_errors:
        print(
            "ERROR: missing preamble style input(s) -- aborting (would produce "
            "a broken PDF on exit 0):",
            file=sys.stderr,
        )
        for e in style_errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "  Fix: ensure 00_shared/latex_styles/ holds the style files, or "
            "that contents/latex_styles resolves to them.",
            file=sys.stderr,
        )
        return False

    # Inject PDF metadata + \scitexBuildID macro (+ the LIVE \writer@version for
    # the clew colophon "Compiled by SciTeX Writer vX.Y.Z") before \begin{document}
    expanded_content = inject_build_metadata(
        expanded_content, build_id, writer_version=resolve_writer_version()
    )

    # Prepend signature (now includes Build ID line)
    signature = generate_signature(source_file=base_tex, build_id=build_id)
    expanded_content = signature + expanded_content

    # Check for SciTeX citation
    # Color codes (matching bash scripts)
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    NC = "\033[0m"  # No Color

    if (
        r"\cite{watanabe2025scitex" in expanded_content
        or r"\citep{watanabe2025scitex" in expanded_content
        or r"\citet{watanabe2025scitex" in expanded_content
    ):
        print(f"{GREEN}{'=' * 78}{NC}")
        print(f"{GREEN}Thank you for citing SciTeX Writer! 🙏{NC}")
        print("")
        print(f"{GREEN}Your support helps maintain this open-source project.{NC}")
        print(f"{GREEN}Citation found: \\cite{{{{watanabe2025scitex}}}}{NC}")
        print(f"{GREEN}{'=' * 78}{NC}")
        print("")
    else:
        print(f"{YELLOW}{'=' * 78}{NC}")
        print(f"{YELLOW}WARN: SciTeX Writer citation not found!{NC}")
        print("")
        print(f"{YELLOW}Please consider citing SciTeX Writer in your manuscript:{NC}")
        print("  \\cite{watanabe2025scitex}")
        print("")
        print(f"{YELLOW}Add this to your bibliography by including:{NC}")
        print("  00_shared/bib_files/scitex-system.bib")
        print("")
        print(f"{YELLOW}Or merge it with your existing bibliography files.{NC}")
        print(f"{YELLOW}{'=' * 78}{NC}")
        print("")

    # Apply tectonic compatibility if enabled
    if tectonic_mode:
        expanded_content = apply_tectonic_compat(expanded_content, base_tex)

    # Inject dark mode styling if enabled
    if dark_mode:
        # Read dark_mode.tex content and inline it (avoid \input path issues)
        dark_mode_file = (
            base_tex.parent.parent / "00_shared" / "latex_styles" / "dark_mode.tex"
        )
        if dark_mode_file.exists():
            with open(dark_mode_file, "r", encoding="utf-8") as f:
                dark_mode_content = f.read()
            # Substitute colors from config env vars (DRY with config/*.yaml)
            color_subs = {
                "1E1E1E": os.getenv("SCITEX_WRITER_DARK_BG", "1E1E1E"),
                "D4D4D4": os.getenv("SCITEX_WRITER_DARK_FG", "D4D4D4"),
                "90C695": os.getenv("SCITEX_WRITER_DARK_LINK_INTERNAL", "90C695"),
                "87CEEB": os.getenv("SCITEX_WRITER_DARK_LINK_CITATION", "87CEEB"),
                "DEB887": os.getenv("SCITEX_WRITER_DARK_LINK_URL", "DEB887"),
            }
            for old_hex, new_hex in color_subs.items():
                dark_mode_content = dark_mode_content.replace(old_hex, new_hex)
            dark_mode_injection = (
                "\n" + DARK_MODE_SENTINEL + "\n" + dark_mode_content + "\n"
            )
        else:
            print(f"WARNING: Dark mode file not found: {dark_mode_file}")
            dark_mode_injection = ""

        # Idempotent: a repeated flatten (running the flattener again on content
        # that already carries the dark-mode block) must NOT stack a second copy
        # before \begin{document} -- that duplicated the override and, pre-fix,
        # surfaced as \REDENDS/\hlref-undefined and a stray \begin{document}.
        if DARK_MODE_SENTINEL in expanded_content:
            dark_mode_injection = ""

        if dark_mode_injection:
            # Inject dark mode styling before the REAL \begin{document}.
            # Anchor to a line-start match, first occurrence only: a plain
            # str.replace() also matched \begin{document} inside COMMENTS (e.g.
            # clew_presentation.tex's "overridable before \begin{document})"),
            # injecting the dark-mode block mid-preamble (before base defs ->
            # "\REDENDS undefined") and de-commenting the tail. A function
            # replacement keeps backslashes in the injection literal.
            expanded_content = re.sub(
                r"(?m)^([ \t]*)\\begin\{document\}",
                lambda m: dark_mode_injection + m.group(0),
                expanded_content,
                count=1,
            )

    # Inject the citation banner (banner-mode compile artifact) at the TOP of
    # page 1 -- right AFTER \begin{document}, before \maketitle -- so a red
    # "UNVERIFIED CITATIONS" box is impossible to miss. Idempotent: skip if the
    # banner sentinel is already present (a reflatten must not stack a copy).
    banner_file = base_tex.parent.parent / CITATION_BANNER_ARTIFACT
    if banner_file.is_file() and CITATION_BANNER_SENTINEL not in expanded_content:
        try:
            banner_tex = banner_file.read_text(encoding="utf-8")
        except OSError:
            banner_tex = ""
        if banner_tex.strip():
            expanded_content = re.sub(
                r"(?m)^([ \t]*)\\begin\{document\}",
                lambda m: m.group(0) + "\n" + banner_tex,
                expanded_content,
                count=1,
            )

    # Inject the OPT-IN per-page bottom-right signature footer before
    # \begin{document}. Enabled when EITHER the standalone opt-in
    # (`signature_footer`) OR the clew-presentation `signature` toggle is active
    # (redesign: one unified knob). DRY single-stamp: the SENTINEL guard inlines
    # the block AT MOST ONCE even when BOTH sources are on. DISTINCT from the
    # always-on invisible pdfcreator metadata (scitex_writer_version.tex).
    clew_signature_on = bool(_CLEW_SIGNATURE_TOGGLE_RE.search(expanded_content))
    if (signature_footer or clew_signature_on) and (
        SIGNATURE_FOOTER_SENTINEL not in expanded_content
    ):
        styles_dir = base_tex.parent.parent / "00_shared" / "latex_styles"
        version = resolve_writer_version()
        footer_injection = build_footer_injection(styles_dir, version)
        if footer_injection:
            if verbose:
                src = "opt-in" if signature_footer else "clew signature toggle"
                print(f"Signature footer: enabled via {src} (v{version})")
            expanded_content = re.sub(
                r"(?m)^([ \t]*)\\begin\{document\}",
                lambda m: footer_injection + m.group(0),
                expanded_content,
                count=1,
            )

    # Inject the clew "Provenance marks" INTRO section near document start when
    # the clew `intro` toggle is active: anchor on \end{frontmatter}, else fall
    # back to just after \begin{document}. Idempotent via the sentinel; gated on
    # the toggle so it is a no-op for a non-clew doc (\clewIntro undefined there).
    if _CLEW_INTRO_TOGGLE_RE.search(expanded_content) and (
        CLEW_INTRO_SENTINEL not in expanded_content
    ):
        intro_injection = "\n" + CLEW_INTRO_SENTINEL + "\n\\clewIntro\n"
        if re.search(r"(?m)^([ \t]*)\\end\{frontmatter\}", expanded_content):
            anchor = r"(?m)^([ \t]*)\\end\{frontmatter\}"
        else:
            anchor = r"(?m)^([ \t]*)\\begin\{document\}"
        if verbose:
            print(f"Clew intro: injected (anchor {anchor})")
        expanded_content = re.sub(
            anchor,
            lambda m: m.group(0) + intro_injection,
            expanded_content,
            count=1,
        )

    # Write output
    try:
        output_tex.parent.mkdir(parents=True, exist_ok=True)
        with open(output_tex, "w", encoding="utf-8") as f:
            f.write(expanded_content)

        if verbose:
            line_count = len(expanded_content.split("\n"))
            print(f"✓ Compiled: {line_count} lines")
            print(f"  Output: {output_tex}")

        # Record the build (#77). doc_type is derived from the
        # SCITEX_WRITER_DOC_TYPE env var that compile.sh sets.
        doc_type = os.getenv("SCITEX_WRITER_DOC_TYPE", "unknown")
        register_build(build_id, doc_type, output_tex)

        return True

    except Exception as e:
        print(f"ERROR: Failed to write output: {e}")
        return False


def main():
    """Command-line interface."""
    import os

    parser = argparse.ArgumentParser(
        description="Compile TeX structure by expanding \\input{} commands"
    )
    parser.add_argument("base_tex", type=Path, help="Base TeX file")
    parser.add_argument("output_tex", type=Path, help="Output compiled TeX file")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")
    parser.add_argument(
        "--dark-mode",
        action="store_true",
        help="Enable dark mode (black background, white text)",
    )
    parser.add_argument(
        "--tectonic-mode",
        action="store_true",
        help="Enable tectonic compatibility (disable incompatible packages)",
    )
    parser.add_argument(
        "--signature-footer",
        action="store_true",
        help="Inject the opt-in visible 'Compiled by scitex-writer v<version>' "
        "page footer (default OFF; also settable via "
        "SCITEX_WRITER_SIGNATURE_FOOTER / config.yaml)",
    )

    args = parser.parse_args()

    # Check environment variables if arguments not provided
    dark_mode = _resolve_dark_mode(args.dark_mode, args.base_tex)
    tectonic_mode = (
        args.tectonic_mode
        or os.getenv("SCITEX_WRITER_ENGINE", "") == "tectonic"
        or os.getenv("SCITEX_WRITER_SELECTED_ENGINE", "") == "tectonic"
    )
    # Project root holds ./config.yaml (same tier the _severity resolver reads).
    # It is base_tex's document-dir parent, matching _theme.read_config_theme.
    project_dir = args.base_tex.resolve().parent.parent
    signature_footer = resolve_signature_footer_enabled(
        args.signature_footer, project_dir
    )

    success = compile_tex_structure(
        base_tex=args.base_tex,
        output_tex=args.output_tex,
        verbose=not args.quiet,
        dark_mode=dark_mode,
        tectonic_mode=tectonic_mode,
        signature_footer=signature_footer,
    )

    exit(0 if success else 1)


if __name__ == "__main__":
    main()

# EOF

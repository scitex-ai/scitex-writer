#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-01-27
# File: src/scitex_writer/_cli/mcp.py

"""MCP CLI commands.

Plain-Python helpers; called from the Click root in `_cli/__init__.py`.
"""

import shutil
import sys

from .. import __version__

CLAUDE_DESKTOP_CONFIG_CLI = """{
  "mcpServers": {
    "scitex-writer": {
      "command": "/path/to/.venv/bin/scitex-writer",
      "args": ["mcp", "start"]
    }
  }
}"""

CLAUDE_DESKTOP_CONFIG_PYTHON = """{
  "mcpServers": {
    "scitex-writer": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "scitex_writer", "mcp", "start"]
    }
  }
}"""


def cmd_start(transport: str = "stdio") -> int:
    """Start the MCP server."""
    from .._mcp import run_server

    run_server(transport=transport)
    return 0


def _get_tool_module(name: str) -> str:
    """Get logical module for a tool name."""
    if name == "usage":
        return "general"
    if "bib" in name:
        return "bib"
    if "compile" in name:
        return "compile"
    if "figure" in name or "pdf_to_images" in name:
        return "figures"
    if "table" in name or "csv_to_latex" in name or "latex_to_csv" in name:
        return "tables"
    if (
        "project" in name
        or "clone" in name
        or "get_pdf" in name
        or "document_types" in name
    ):
        return "project"
    if "guideline" in name:
        return "guidelines"
    if "prompts" in name:
        return "prompts"
    return "general"


def _style(text: str, fg: str = None, bold: bool = False) -> str:
    """Apply ANSI color styling."""
    if not sys.stdout.isatty():
        return text
    codes = {
        "green": "\033[32m",
        "cyan": "\033[36m",
        "yellow": "\033[33m",
        "magenta": "\033[35m",
        "white": "\033[37m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }
    prefix = ""
    if bold:
        prefix += codes["bold"]
    if fg and fg in codes:
        prefix += codes[fg]
    return f"{prefix}{text}{codes['reset']}" if prefix else text


def _format_tool_signature(tool, compact: bool = False, indent: str = "  ") -> str:
    """Format tool as Python-like function signature with colors."""
    params = []
    if hasattr(tool, "parameters") and tool.parameters:
        schema = tool.parameters
        props = schema.get("properties", {})
        required = schema.get("required", [])
        for name, info in props.items():
            ptype = info.get("type", "any")
            default = info.get("default")
            # Color: name in white bold, type in cyan, default in yellow
            name_s = _style(name, "white", bold=True)
            type_s = _style(ptype, "cyan")
            if name in required:
                params.append(f"{name_s}: {type_s}")
            elif default is not None:
                def_str = repr(default) if len(repr(default)) < 20 else "..."
                def_s = _style(f"= {def_str}", "yellow")
                params.append(f"{name_s}: {type_s} {def_s}")
            else:
                def_s = _style("= None", "yellow")
                params.append(f"{name_s}: {type_s} {def_s}")

    # All MCP tools return a standardized Result envelope
    ret_type = (
        f" -> {_style('Result', 'magenta')}"
        f"{_style('{success, data, error, hints_on_error}', 'yellow')}"
    )

    # Function name in green
    name_s = _style(tool.name, "green")
    if compact or len(params) <= 2:
        return f"{indent}{name_s}({', '.join(params)}){ret_type}"
    else:
        param_indent = indent + "    "
        params_str = ",\n".join(f"{param_indent}{p}" for p in params)
        return f"{indent}{name_s}(\n{params_str}\n{indent}){ret_type}"


def _format_param_names(tool, indent: str = "    ") -> str:
    """Format parameter names only (no types), for -vv level."""
    if not hasattr(tool, "parameters") or not tool.parameters:
        return ""
    props = tool.parameters.get("properties", {})
    required = tool.parameters.get("required", [])
    if not props:
        return ""
    parts = []
    for name in props:
        name_s = _style(name, "white", bold=True)
        if name not in required:
            name_s += _style("?", "yellow")
        parts.append(name_s)
    return f"{indent}params: {', '.join(parts)}"


def cmd_list_tools(
    verbose: int = 0,
    compact: bool = False,
    module: str = None,
    as_json: bool = False,
) -> int:
    """List all available MCP tools (figrecipe-compatible format)."""
    from .._mcp import mcp

    module_filter = module

    import asyncio

    tool_objs = asyncio.run(mcp.list_tools())
    tool_map = {t.name: t for t in tool_objs}
    tools = list(tool_map.keys())
    total = len(tools)

    # Group by logical module
    modules = {}
    for tool_name in sorted(tools):
        module = _get_tool_module(tool_name)
        if module not in modules:
            modules[module] = []
        modules[module].append(tool_name)

    # Filter by module if specified
    if module_filter:
        module_filter = module_filter.lower()
        if module_filter not in modules:
            sys.stdout.write(f"ERROR: Unknown module '{module_filter}'\n")
            sys.stdout.write(f"Available modules: {', '.join(sorted(modules.keys()))}\n")
            return 1
        modules = {module_filter: modules[module_filter]}

    if as_json:
        import json

        from scitex_dev import RESULT_SCHEMA

        output = {
            "name": "scitex-writer",
            "result_envelope": RESULT_SCHEMA,
            "total": sum(len(t) for t in modules.values()),
            "modules": {},
        }
        for mod, tool_list in modules.items():
            output["modules"][mod] = {
                "count": len(tool_list),
                "tools": tool_list,
            }
        sys.stdout.write(json.dumps(output, indent=2) + "\n")
        return 0

    sys.stdout.write(_style("SciTeX Writer MCP: scitex-writer", "cyan", bold=True) + "\n")
    sys.stdout.write(f"Tools: {total} ({len(modules)} modules)\n")
    sys.stdout.write("Returns: Result{success, data, error, error_code, context, hints_on_error}\n")
    sys.stdout.write("\n")

    for module in sorted(modules.keys()):
        mod_tools = sorted(modules[module])
        sys.stdout.write(_style(f"{module}: {len(mod_tools)} tools", "green", bold=True) + "\n")
        for tool_name in mod_tools:
            tool_obj = tool_map.get(tool_name)

            if verbose == 0:
                # Names only (default)
                sys.stdout.write(f"  {tool_name}\n")
            elif verbose == 1:
                # -v: Name + one-line description
                sys.stdout.write(f"  {tool_name}\n")
                if tool_obj and tool_obj.description:
                    desc = tool_obj.description.split("\n")[0].strip()
                    sys.stdout.write(f"    {_style(desc, 'yellow')}\n")
            elif verbose == 2:
                # -vv: Name + one-line description + parameter names
                sys.stdout.write(f"  {tool_name}\n")
                if tool_obj and tool_obj.description:
                    desc = tool_obj.description.split("\n")[0].strip()
                    sys.stdout.write(f"    {_style(desc, 'yellow')}\n")
                if tool_obj:
                    param_line = _format_param_names(tool_obj)
                    if param_line:
                        sys.stdout.write(param_line + "\n")
            else:
                # -vvv: Full detail -- signature with types + full description
                sig = (
                    _format_tool_signature(tool_obj, compact=compact)
                    if tool_obj
                    else f"  {tool_name}"
                )
                sys.stdout.write(sig + "\n")
                if tool_obj and tool_obj.description:
                    for line in tool_obj.description.strip().split("\n"):
                        sys.stdout.write(f"    {line}\n")
                sys.stdout.write("\n")
        sys.stdout.write("\n")

    return 0


def cmd_doctor() -> int:
    """Check MCP server health and configuration."""
    sys.stdout.write(f"scitex-writer {__version__}\n")
    sys.stdout.write("Health Check\n")
    sys.stdout.write("=" * 40 + "\n")

    checks = []

    try:
        import fastmcp

        checks.append(("fastmcp", True, fastmcp.__version__))
    except ImportError:
        checks.append(("fastmcp", False, "not installed"))

    try:
        import asyncio

        from .._mcp import mcp

        tool_count = len(asyncio.run(mcp.list_tools()))
        checks.append(("MCP server", True, f"{tool_count} tools"))
    except Exception as e:
        checks.append(("MCP server", False, str(e)))

    scitex_path = shutil.which("scitex-writer")
    if scitex_path:
        checks.append(("CLI", True, scitex_path))
    else:
        checks.append(("CLI", False, "not in PATH"))

    all_ok = True
    for name, ok, info in checks:
        status = "✓" if ok else "✗"
        if not ok:
            all_ok = False
        sys.stdout.write(f"  {status} {name}: {info}\n")

    sys.stdout.write("\n")
    if all_ok:
        sys.stdout.write("All checks passed!\n")
    else:
        sys.stdout.write("Some checks failed. Run 'pip install scitex-writer' to fix.\n")

    return 0 if all_ok else 1


def cmd_config() -> int:
    """Show Claude Desktop configuration snippet."""
    sys.stdout.write(f"scitex-writer {__version__}\n")
    sys.stdout.write("Add this to your Claude Desktop config file:\n")
    sys.stdout.write("  macOS: ~/Library/Application Support/Claude/claude_desktop_config.json\n")
    sys.stdout.write("  Linux: ~/.config/Claude/claude_desktop_config.json\n")

    scitex_path = shutil.which("scitex-writer")
    if scitex_path:
        sys.stdout.write(f"Your installation path: {scitex_path}\n")

    sys.stdout.write("Option 1: CLI command (replace path with your installation)\n")
    sys.stdout.write(CLAUDE_DESKTOP_CONFIG_CLI + "\n")
    sys.stdout.write("\nOption 2: Python module (replace path with your installation)\n")
    sys.stdout.write(CLAUDE_DESKTOP_CONFIG_PYTHON + "\n")
    return 0


# EOF

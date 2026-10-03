#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-01-30
# File: src/scitex_writer/_cli/introspect.py

"""Introspection CLI commands for scitex-writer (figrecipe-compatible format).

Plain-Python helpers; called from the Click root in `_cli/__init__.py`.
"""

import importlib
import inspect
import sys

import scitex_logging as slogging

log = slogging.getLogger(__name__)

# Color mapping for types (matching figrecipe)
TYPE_COLORS = {"M": "blue", "C": "magenta", "F": "green", "V": "cyan"}

# ANSI color codes
ANSI = {
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "green": "\033[32m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "yellow": "\033[33m",
    "reset": "\033[0m",
    "bold": "\033[1m",
}


def _style(text: str, fg: str = None, bold: bool = False) -> str:
    """Apply ANSI styling to text."""
    if not sys.stdout.isatty():
        return text
    prefix = ""
    if bold:
        prefix += ANSI["bold"]
    if fg and fg in ANSI:
        prefix += ANSI[fg]
    if prefix:
        return f"{prefix}{text}{ANSI['reset']}"
    return text


def _simplify_type(ann) -> str:
    """Simplify type annotation to base type name like figrecipe."""
    import types
    import typing

    # Handle Python 3.10+ UnionType (str | None)
    if isinstance(ann, types.UnionType):
        args = typing.get_args(ann)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and type(None) in args:
            return "Optional"
        return "Union"

    # Get origin for generic types (Optional, Union, List, Dict, etc.)
    origin = typing.get_origin(ann)
    if origin is not None:
        # For Union types (including Optional which is Union[X, None])
        if origin is typing.Union:
            args = typing.get_args(ann)
            # Check if it's Optional (Union with None)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1 and type(None) in args:
                return "Optional"
            return "Union"
        # For other generic types, return the origin name
        return origin.__name__ if hasattr(origin, "__name__") else str(origin)

    # For simple types
    if hasattr(ann, "__name__"):
        return ann.__name__

    # Fallback: string representation cleaned up
    type_str = str(ann)
    type_str = type_str.replace("typing.", "")
    # Further simplify: extract just the base type
    if "[" in type_str:
        type_str = type_str.split("[")[0]
    return type_str


def _format_python_signature(func, multiline: bool = True, indent: str = "  ") -> tuple:
    """Format Python function signature with colors matching figrecipe.

    Returns (name_colored, signature_colored)
    """
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return _style(func.__name__, "green", bold=True), ""

    params = []
    for name, param in sig.parameters.items():
        # Get type annotation
        if param.annotation != inspect.Parameter.empty:
            type_str = _simplify_type(param.annotation)
        else:
            type_str = None

        # Get default value
        if param.default != inspect.Parameter.empty:
            default = param.default
            def_str = repr(default) if len(repr(default)) < 20 else "..."
            if type_str:
                p = f"{_style(name, 'white', bold=True)}: {_style(type_str, 'cyan')} = {_style(def_str, 'yellow')}"
            else:
                p = f"{_style(name, 'white', bold=True)} = {_style(def_str, 'yellow')}"
        else:
            if type_str:
                p = f"{_style(name, 'white', bold=True)}: {_style(type_str, 'cyan')}"
            else:
                p = _style(name, "white", bold=True)
        params.append(p)

    # Return type
    ret_str = ""
    if sig.return_annotation != inspect.Parameter.empty:
        ret = sig.return_annotation
        ret_name = ret.__name__ if hasattr(ret, "__name__") else str(ret)
        ret_name = ret_name.replace("typing.", "")
        ret_str = f" -> {_style(ret_name, 'magenta')}"

    name_s = _style(func.__name__, "green", bold=True)

    if multiline and len(params) > 2:
        param_indent = indent + "    "
        params_str = ",\n".join(f"{param_indent}{p}" for p in params)
        sig_s = f"(\n{params_str}\n{indent}){ret_str}"
    else:
        sig_s = f"({', '.join(params)}){ret_str}"

    return name_s, sig_s


def _get_api_tree(module, max_depth: int = 5, docstring: bool = False) -> list[dict]:
    """Get API tree for a module with types and signatures.

    Returns list of dicts with: Name, Type, Depth, Docstring (optional)
    """
    results = []

    def _visit(obj, name: str, depth: int, visited: set):
        if depth > max_depth:
            return
        obj_id = id(obj)
        if obj_id in visited:
            return
        visited.add(obj_id)

        # Determine type
        if inspect.ismodule(obj):
            obj_type = "M"
        elif inspect.isclass(obj):
            obj_type = "C"
        elif callable(obj):
            obj_type = "F"
        else:
            obj_type = "V"

        entry = {"Name": name, "Type": obj_type, "Depth": depth}
        if docstring:
            entry["Docstring"] = inspect.getdoc(obj) or ""
        results.append(entry)

        # Recurse into modules
        if inspect.ismodule(obj) and depth < max_depth:
            if hasattr(obj, "__all__"):
                members = [(n, getattr(obj, n, None)) for n in obj.__all__]
            else:
                members = [
                    (n, v) for n, v in inspect.getmembers(obj) if not n.startswith("_")
                ]
            for member_name, member_obj in members:
                if member_obj is not None:
                    _visit(member_obj, f"{name}.{member_name}", depth + 1, visited)

    _visit(module, module.__name__.split(".")[-1], 0, set())
    return results


def cmd_api(
    dotted_path: str,
    verbose: int = 0,
    max_depth: int = 5,
    as_json: bool = False,
) -> int:
    """List API tree of a Python module."""
    dotted_path = dotted_path.replace("-", "_")

    try:
        module = importlib.import_module(dotted_path)
    except ImportError as e:
        log.error(f"Error importing {dotted_path}: {e}")
        return 1

    df = _get_api_tree(module, max_depth=max_depth, docstring=(verbose >= 1))

    if as_json:
        import json

        sys.stdout.write(json.dumps(df, indent=2) + "\n")
        return 0

    sys.stdout.write(_style(f"API tree of {dotted_path} ({len(df)} items):", fg="cyan") + "\n")
    legend = " ".join(
        _style(f"[{t}]={n}", fg=TYPE_COLORS[t])
        for t, n in [
            ("M", "Module"),
            ("C", "Class"),
            ("F", "Function"),
            ("V", "Variable"),
        ]
    )
    sys.stdout.write(f"Legend: {legend}\n")

    for row in df:
        indent = "  " * row["Depth"]
        t = row["Type"]
        type_s = _style(f"[{t}]", fg=TYPE_COLORS.get(t, "yellow"))
        name = row["Name"].split(".")[-1]

        if t == "F":
            try:
                # Get the actual function
                parts = row["Name"].split(".")
                obj = module
                for part in parts[1:]:  # Skip module name
                    obj = getattr(obj, part, None)
                    if obj is None:
                        break
                if obj and callable(obj):
                    name_s, sig_s = _format_python_signature(obj, indent=indent)
                    sys.stdout.write(f"{indent}{type_s} {name_s}{sig_s}\n")
                else:
                    name_s = _style(name, "green", bold=True)
                    sys.stdout.write(f"{indent}{type_s} {name_s}\n")
            except Exception:
                name_s = _style(name, "green", bold=True)
                sys.stdout.write(f"{indent}{type_s} {name_s}\n")
        else:
            name_s = _style(name, fg=TYPE_COLORS.get(t, "white"), bold=True)
            sys.stdout.write(f"{indent}{type_s} {name_s}\n")

        if verbose >= 1 and row.get("Docstring"):
            if verbose == 1:
                doc = row["Docstring"].split("\n")[0][:60]
                sys.stdout.write(f"{indent}    - {doc}\n")
            else:
                for ln in row["Docstring"].split("\n"):
                    sys.stdout.write(f"{indent}    {ln}\n")

    return 0


def cmd_list_python_apis(
    verbose: int = 0,
    max_depth: int = 5,
    as_json: bool = False,
) -> int:
    """List Python APIs (alias for introspect show-api scitex_writer)."""
    return cmd_api(
        "scitex_writer", verbose=verbose, max_depth=max_depth, as_json=as_json
    )


# EOF

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_utils/_csv_latex.py

"""
CSV <-> LaTeX table conversion utilities.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Union

from scitex_logging import getLogger

logger = getLogger(__name__)


def _fit_tabular(latex: str) -> str:
    r"""Wrap a tabular so a wide table shrinks to \linewidth instead of
    overflowing the page (and vanishing from the PDF).

    Scales DOWN only when the table's natural width exceeds \linewidth; narrow
    tables are left untouched. Self-contained — uses only \resizebox (graphicx,
    always loaded by the scitex preamble), so no extra package or preamble
    macro is required. longtable spans pages and cannot be boxed, so callers
    skip it.
    """
    if "\\resizebox" in latex:
        return latex  # already wrapped — idempotent, never double-wrap
    open_box = (
        r"\resizebox{\ifdim\width>\linewidth\linewidth\else\width\fi}{!}{%" + "\n"
    )
    return re.sub(
        r"(\\begin\{tabular\}.*?\\end\{tabular\})",
        lambda m: open_box + m.group(1) + "\n}",
        latex,
        count=1,
        flags=re.DOTALL,
    )


def csv2latex(
    csv_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    caption: Optional[str] = None,
    label: Optional[str] = None,
    escape: bool = True,
    longtable: bool = False,
    index: bool = False,
    column_format: Optional[str] = None,
    auto_fit: bool = True,
    **kwargs,
) -> str:
    """
    Convert CSV file to LaTeX table.

    Parameters
    ----------
    csv_path : str or Path
        Path to CSV file
    output_path : str or Path, optional
        If provided, save LaTeX to this file
    caption : str, optional
        Table caption
    label : str, optional
        Table label for referencing
    escape : bool, default True
        Escape special LaTeX characters
    longtable : bool, default False
        Use longtable environment for multi-page tables
    index : bool, default False
        Include DataFrame index in output
    column_format : str, optional
        LaTeX column format (e.g., 'lcr', 'l|cc|r')
    auto_fit : bool, default True
        Wrap the tabular so a wider-than-\\linewidth table shrinks to fit
        (prevents page overflow / an invisible table). Ignored for longtable.
    **kwargs
        Additional arguments passed to pandas.DataFrame.to_latex()

    Returns
    -------
    str
        LaTeX table string

    Examples
    --------
    >>> latex = csv2latex("data.csv", caption="Results", label="tab:results")
    >>> csv2latex("data.csv", "table.tex")  # Save to file
    """
    import pandas as pd

    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Load CSV
    df = pd.read_csv(csv_path)

    # Build to_latex arguments
    latex_kwargs = {
        "index": index,
        "escape": escape,
        "caption": caption,
        "label": label,
    }

    if longtable:
        latex_kwargs["longtable"] = True

    if column_format:
        latex_kwargs["column_format"] = column_format

    # Merge with user kwargs
    latex_kwargs.update(kwargs)

    # Convert to LaTeX
    latex_content = df.to_latex(**latex_kwargs)

    # Shrink wide tables to the text width so they never overflow (and vanish).
    if auto_fit and not longtable:
        latex_content = _fit_tabular(latex_content)

    # Save if output path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(latex_content)
        logger.info(f"Saved LaTeX table to {output_path}")

    return latex_content


def latex2csv(
    latex_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    table_index: int = 0,
):
    """
    Convert LaTeX table to CSV/DataFrame.

    Parameters
    ----------
    latex_path : str or Path
        Path to LaTeX file containing table
    output_path : str or Path, optional
        If provided, save CSV to this file
    table_index : int, default 0
        Which table to extract if multiple tables exist

    Returns
    -------
    pd.DataFrame
        Extracted table as DataFrame

    Examples
    --------
    >>> df = latex2csv("table.tex")
    >>> df = latex2csv("table.tex", "output.csv")
    """
    import pandas as pd

    latex_path = Path(latex_path)
    if not latex_path.exists():
        raise FileNotFoundError(f"LaTeX file not found: {latex_path}")

    with open(latex_path) as f:
        content = f.read()

    # Extract table content (between \begin{tabular} and \end{tabular})
    # Also handle longtable
    patterns = [
        r"\\begin\{tabular\}.*?\n(.*?)\\end\{tabular\}",
        r"\\begin\{longtable\}.*?\n(.*?)\\end\{longtable\}",
    ]

    tables = []
    for pattern in patterns:
        matches = re.findall(pattern, content, re.DOTALL)
        tables.extend(matches)

    if not tables:
        raise ValueError("No table found in LaTeX file")

    if table_index >= len(tables):
        raise IndexError(
            f"Table index {table_index} out of range. Found {len(tables)} tables."
        )

    table_content = tables[table_index]

    # Parse table rows
    rows = []
    for line in table_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("\\"):
            continue
        if "&" in line:
            # Remove trailing \\ and split by &
            line = re.sub(r"\\\\.*$", "", line)
            cells = [cell.strip() for cell in line.split("&")]
            rows.append(cells)

    if not rows:
        raise ValueError("Could not parse table rows")

    # Create DataFrame (first row as header if it looks like headers)
    if len(rows) > 1:
        df = pd.DataFrame(rows[1:], columns=rows[0])
    else:
        df = pd.DataFrame(rows)

    # Save if output path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info(f"Saved CSV to {output_path}")

    return df


__all__ = ["csv2latex", "latex2csv"]

# EOF

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-02-04
# File: src/scitex_writer/_usage.py

"""Usage guide content for scitex-writer.

This module contains the usage documentation text, separate from branding logic.
"""

from ._core._branding import BRAND_ALIAS, BRAND_NAME, get_branded_import_example

_USAGE_TEMPLATE = """
================================================================================
{brand_name} - LaTeX Manuscript Compilation System
================================================================================

Setup:
  scitex-writer create-project my-paper     # creates my-paper/.scitex/writer
  cd my-paper

<SCITEX_WRITER_ROOT> = Directory where compile.sh is located
                       (my-paper/.scitex/writer for a project created above)

================================================================================
Project Structure
================================================================================

  <SCITEX_WRITER_ROOT>/
  ├── compile.sh           # Main compilation script
  ├── 00_shared/           # Shared metadata (title, authors, keywords, bib_files/)
  ├── 01_manuscript/       # Main manuscript
  ├── 02_supplementary/    # Supplementary materials
  └── 03_revision/         # Revision responses

================================================================================
Content Files (01_manuscript/contents/)
================================================================================

  abstract.tex        - Abstract text
  introduction.tex    - Introduction section
  methods.tex         - Methods section
  results.tex         - Results section
  discussion.tex      - Discussion section

  Just write plain LaTeX content. No \\begin{{document}} needed.

================================================================================
Bibliography (00_shared/bib_files/)
================================================================================

  Workflow:
    1. SAVE authentic .bib from reliable sources -> bib_files/<descriptive>.bib
    2. COMPILE -> system auto-merges all .bib with smart deduplication
    3. CITE -> use any key from any file in bib_files/

  CRITICAL: NO SYNTHETIC/FAKE CITATIONS
    - NEVER create non-existent bibliography entries
    - NEVER hallucinate author names, titles, or DOIs
    - ALL entries MUST be retrieved using scitex MCP tools:

        scitex - crossref_search        # Search CrossRef (167M+ works)
        scitex - crossref_search_by_doi # Lookup by DOI
        scitex - openalex_search        # Search OpenAlex (280M+ works)
        scitex - openalex_search_by_id  # Lookup by OpenAlex ID

    - If unsure about a citation, DO NOT add it

  Auto-Merge Features (battery-included):
    - All .bib files in bib_files/ are merged automatically
    - Smart deduplication by DOI and title+year
    - No manual merge needed

  IMPORTANT: BibTeX entries are SINGLE SOURCE OF TRUTH
    - NEVER modify existing citation keys
    - Use keys exactly as they appear in .bib files
    - Check existing keys: grep -r "AuthorName" 00_shared/bib_files/

  Directory Structure (keep clean):
    00_shared/bib_files/
    ├── bibliography.bib      # AUTO-GENERATED (do not edit)
    ├── my_papers.bib         # Your own publications
    ├── field_background.bib  # Core field references
    ├── methods_refs.bib      # Methods/tools citations
    └── related_work.bib      # Related work citations

  Files to AVOID:
    - enriched_*.bib, merged_*.bib, by_*.bib, *.json

  How to Cite in LaTeX:
    \\cite{{Smith2024_DeepLearning}}                    -> [1]
    \\citep{{Smith2024_DeepLearning}}                  -> (Smith et al., 2024)
    \\citet{{Smith2024_DeepLearning}}                  -> Smith et al. (2024)

================================================================================
Figures (01_manuscript/contents/figures/caption_and_media/)
================================================================================

  File Naming Convention (REQUIRED):
    <NN>_<descriptive_name>.<ext>    - Image file
    <NN>_<descriptive_name>.tex      - Caption file (MUST match image basename)

  Example:
    01_neural_network.png            - Image file
    01_neural_network.tex            - Caption file

  Caption File Format (01_neural_network.tex):
    %% Figure caption
    \\caption{{Architecture of the neural network model.}}
    \\label{{fig:01_neural_network}}

  Label Convention:
    \\label{{fig:<filename_without_extension>}}
    - Prefix: fig:
    - Filename without extension (exactly as named)

  How to Reference in Text:
    Figure~\\ref{{fig:01_neural_network}}       -> Figure 1
    Figure~\\ref{{fig:01_neural_network}}A      -> Figure 1A (for panels)

  Supported Formats:
    PNG, JPEG, PDF, SVG, TIFF, Mermaid (.mmd)
    SVG/Mermaid auto-convert to PDF during compilation

  Figure Style (REQUIRED for consistency):
    import scitex
    scitex.plt.load_style("SCITEX")
    fig, ax = scitex.plt.subplots(**scitex.plt.presets.SCITEX_STYLE)

    Or with figrecipe:
    import figrecipe as fr
    fr.load_style("SCITEX")

  WARNING: Strict naming is REQUIRED for compilation
    - Image and caption files MUST have identical basenames
    - Label MUST match filename (fig:<filename>)
    - Mismatched names cause compilation FAILURE

================================================================================
Tables (01_manuscript/contents/tables/caption_and_media/)
================================================================================

  File Naming Convention (REQUIRED):
    <NN>_<descriptive_name>.csv      - Data file (CSV format)
    <NN>_<descriptive_name>.tex      - Caption file (MUST match CSV basename)

  Example:
    01_performance_metrics.csv       - Data file
    01_performance_metrics.tex       - Caption file

  CSV Format:
    Column1,Column2,Column3
    Value1,Value2,Value3
    Value4,Value5,Value6

  Caption File Format (01_performance_metrics.tex):
    %% Table caption
    \\caption{{Performance metrics across experimental conditions.}}
    \\label{{tab:01_performance_metrics}}

  Label Convention:
    \\label{{tab:<filename_without_extension>}}
    - Prefix: tab:
    - Filename without extension (exactly as named)

  How to Reference in Text:
    Table~\\ref{{tab:01_performance_metrics}}   -> Table 1

  CSV auto-converts to LaTeX tabular during compilation.

  WARNING: Strict naming is REQUIRED for compilation
    - CSV and caption files MUST have identical basenames
    - Label MUST match filename (tab:<filename>)
    - Mismatched names cause compilation FAILURE

================================================================================
Four Interfaces
================================================================================

Python API:
  {import_example}
  {alias}.usage()                        # Show this guide
  {alias}.compile.manuscript("./my-paper")
  {alias}.project.clone("./new-paper")
  {alias}.gui("./my-paper")             # Launch GUI editor

CLI:
  scitex-writer usage                    # Show this guide
  scitex-writer compile manuscript .     # Compile manuscript
  scitex-writer mcp list-tools           # List MCP tools
  scitex-writer gui                      # Launch GUI editor

GUI (uv pip install 'scitex-writer[all]'):
  scitex-writer gui ./my-paper           # Browser-based editor

MCP Tool:
  writer_usage()                         # Returns this guide

================================================================================
Compilation
================================================================================

Shell (BASH_ENV workaround for AI agents):
  env -u BASH_ENV /bin/bash -c '<SCITEX_WRITER_ROOT>/compile.sh manuscript --draft'

Makefile (recommended):
  make manuscript          # Compile manuscript
  make supplementary       # Compile supplementary
  make revision            # Compile revision
  make all                 # Compile all documents
  make draft               # Fast draft (skips bibliography)

  make manuscript-watch    # Watch manuscript
  make supplementary-watch # Watch supplementary
  make revision-watch      # Watch revision
  make all-watch           # Watch all documents

Watch Mode (auto-recompile on file changes):
  ./compile.sh manuscript --watch
  ./compile.sh -m -w --no_figs    # Watch with speed options

Options:
  --watch, -w   Auto-recompile on file changes (manuscript only)
  --draft       Skip bibliography processing (faster)
  --no_figs     Skip figure processing
  --no_tables   Skip table processing
  --no_diff     Skip diff generation
  --dark_mode   Dark background for figures
  --quiet       Suppress output

Output:
  01_manuscript/manuscript.pdf
  01_manuscript/manuscript_diff.pdf (tracked changes)

================================================================================
Highlighting for User Review
================================================================================

  \\hl{{[PLACEHOLDER: description]}}  - Content user must fill in
  \\hl{{[CHECK: reason]}}             - Claims/facts to verify

================================================================================
Supplementary Materials (02_supplementary/)
================================================================================

  Same structure as 01_manuscript/.

  IMPORTANT: File Naming Uses NUMERIC Prefixes (Same as Manuscript)
    The preprocessing scripts require [0-9]* pattern for all document types.
    Use numeric prefixes (01_, 02_, ...) for filenames, NOT S1_, S2_.

  File Naming for Supplementary (REQUIRED):
    01_descriptive_name.png          # Image file (numeric prefix)
    01_descriptive_name.tex          # Caption file (must match)
    01_descriptive_name.csv          # Table data (numeric prefix)

  Label Convention for Supplementary:
    Use S-prefix in LABELS only (not filenames) for clarity:
    \\label{{fig:S01_descriptive_name}}  # Supplementary Figure S1
    \\label{{tab:S01_descriptive_name}}  # Supplementary Table S1

    Or keep numeric labels and add "Supplementary" in text references:
    \\label{{fig:01_descriptive_name}}   # Referenced as "Supplementary Figure 1"

  Cross-Referencing (Main -> Supplementary):
    In 01_manuscript/contents/*.tex:
      Supplementary Figure~\\ref{{fig:S01_descriptive_name}}
      Supplementary Table~\\ref{{tab:S01_descriptive_name}}
      (see Supplementary Methods for details)

  Cross-Referencing (Supplementary -> Main):
    In 02_supplementary/contents/*.tex:
      (as described in the main text)
      Figure~\\ref{{fig:01_neural_network}} in the main manuscript

  Note: Cross-references work because of xr-hyper package setup
        in base.tex with \\link command

================================================================================
Writing Guidelines
================================================================================

  Content Standards:
    - Write coherent paragraphs, NOT bullet lists
    - One claim per paragraph, topic sentence first
    - All claims must have citations or evidence
    - Follow IMRAD structure (Intro, Methods, Results, Discussion)

  Citation Requirements:
    - Every factual claim needs a citation
    - Cite primary sources, not reviews (when possible)
    - Verify all citation keys exist in bib_files/

  Figure Requirements:
    - Figures must be referenced in text before appearing
    - Captions must be self-explanatory (reader understands without main text)
    - Include panel labels (A, B, C) for multi-panel figures
    - Define all abbreviations in caption

  Table Requirements:
    - Tables must be referenced in text before appearing
    - Define abbreviations in caption or footnote
    - Use consistent decimal places and units

================================================================================
Journal Specifications (MUST CHECK BEFORE WRITING)
================================================================================

  Word/Character Limits:
    - Abstract: typically 150-300 words
    - Main text: varies (3000-8000 words common)
    - Check journal's "Instructions for Authors"

  Figure/Table Limits:
    - Many journals limit to 6-8 figures
    - Combined figure+table limit may apply
    - Excess goes to Supplementary Materials

  Reference Limits:
    - Some journals cap at 40-60 references
    - Check if online-only references allowed

  Section Requirements:
    - Some journals require specific sections (e.g., "Data Availability")
    - Author contributions format (CRediT taxonomy)
    - Conflict of interest statement

  Format Requirements:
    - Line numbering (compile with --draft for this)
    - Double spacing requirements
    - Figure resolution (typically 300 DPI minimum)

================================================================================
Quality Checklist (Before Compilation)
================================================================================

  [ ] No placeholder text remaining (\\hl{{[PLACEHOLDER:...]}})
  [ ] All \\hl{{[CHECK:...]}} items verified
  [ ] All figures referenced in text: Figure~\\ref{{fig:...}}
  [ ] All tables referenced in text: Table~\\ref{{tab:...}}
  [ ] All citations exist in bib_files/: \\cite{{...}}
  [ ] No bullet lists in main text (use paragraphs)
  [ ] IMRAD sections complete and coherent
  [ ] Captions are self-explanatory
"""


def get_usage() -> str:
    """Get the usage guide with branding applied.

    Returns
    -------
    str
        Formatted usage guide string.
    """
    return _USAGE_TEMPLATE.format(
        brand_name=BRAND_NAME,
        import_example=get_branded_import_example(),
        alias=BRAND_ALIAS,
    )


__all__ = ["get_usage"]

# EOF

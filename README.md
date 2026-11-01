<!-- ---
!-- File: README.md
!-- --- -->

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-logo-banner.png" alt="SciTeX Writer" width="400">
  </a>
</p>

# SciTeX Writer

<!-- scitex-badges:start -->
<p align="center">
  <a href="https://pypi.org/project/scitex-writer/"><img src="https://img.shields.io/pypi/v/scitex-writer?label=pypi" alt="pypi"></a>
  <a href="https://pypi.org/project/scitex-writer/"><img src="https://img.shields.io/pypi/pyversions/scitex-writer?label=python" alt="python"></a>
  <a href="https://github.com/ywatanabe1989/scitex-writer/actions/workflows/rtd-sphinx-build-on-ubuntu-latest.yml"><img src="https://img.shields.io/github/actions/workflow/status/ywatanabe1989/scitex-writer/rtd-sphinx-build-on-ubuntu-latest.yml?branch=develop&label=docs" alt="docs"></a>
  <a href='https://scitex-writer.readthedocs.io/en/latest/'><img src='https://img.shields.io/readthedocs/scitex-writer?label=docs' alt='Read the Docs'></a>
</p>
<p align="center">
  <a href="https://github.com/ywatanabe1989/scitex-writer/actions/workflows/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml"><img src="https://img.shields.io/github/actions/workflow/status/ywatanabe1989/scitex-writer/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml?branch=develop&label=tests" alt="tests"></a>
  <a href="https://codecov.io/gh/ywatanabe1989/scitex-writer"><img src="https://img.shields.io/codecov/c/github/ywatanabe1989/scitex-writer/develop?label=cov" alt="cov"></a>
</p>
<!-- scitex-badges:end -->

<p align="center">
  <a href="https://scitex.ai">scitex.ai</a> · <a href="https://scitex-writer.readthedocs.io/">docs</a> · <code>uv pip install scitex-writer[all]</code>
</p>

---

**LaTeX compilation system for scientific manuscripts with automatic versioning, diff generation, and cross-platform reproducibility.**

Part of the [SciTeX](https://scitex.ai) ecosystem — empowers both human researchers and AI agents.

## Problem and Solution


| # | Problem | Solution |
|---|---------|----------|
| 1 | **LaTeX compilation is fragile** -- bib, figs, tables, cross-refs, supplement each have their own failure mode | **`scitex writer compile`** -- one command runs bibtex → latex → bibtex → latex twice; handles supplement + revision diffs |
| 2 | **Figures drift from manuscript** -- author renumbers a figure; half the references go stale; `\ref{}` silently prints `??` | **Reference check + float-order audit** -- `writer_check_references` + `writer_check_float_order` catch dangling `\ref{}` before submission |
| 3 | **Manuscript claims uncheckable** -- a paper asserts "t(58) = 2.34, p = .021"; reviewer has no way to verify | **Clew-backed claims** -- `writer_add_claim` binds each assertion to a source session + file hash; `writer_render_claims` exposes the verification DAG |

## Quick Start

```bash
git clone https://github.com/ywatanabe1989/scitex-writer.git my-paper
cd my-paper && make manuscript   # or: ./compile.sh manuscript
```

## Demo

<p align="center">
<p align="center">
  <img src="docs/demo-manuscript-light.png" alt="Light Mode" width="380"/>
</p>
<sub><b>Figure 1.</b> Compiled manuscript preview, light mode (default).</sub>

<p align="center">
  <img src="docs/demo-manuscript-dark.png" alt="Dark Mode" width="380"/>
</p>
<sub><b>Figure 2.</b> Compiled manuscript preview, dark mode (<code>--dark-mode</code>).</sub>
<p align="center">
  <em>Light mode (default) and dark mode (<code>--dark-mode</code>)</em>
</p>

<p align="center">
  <a href="https://scitex.ai/demos/watch/scitex-writer/">
    <img src="examples/scitex-writer-v2.2.0-demo-thumbnail.png" alt="Demo Video" width="600"/>
  </a>
</p>
<p align="center">
  <em>Demo video with AI agent</em>
</p>
<sub><b>Figure 3.</b> Demo video: an AI agent compiling a manuscript with scitex-writer.</sub>

## Installation

```bash
uv pip install "scitex-writer[all]"
```

<details>
<summary><strong>Extras</strong></summary>

| Extra | Contents |
|-------|----------|
| `all` | Everything: desktop GUI, workspace shell, scholar checks, plus `dev` + `docs` |
| `dev` | Test suite: pytest, coverage, xdist, pre-commit |
| `docs` | Sphinx docs build: sphinx, theme, myst-parser, copybutton |

Bare `pip install scitex-writer` gives the compile engine only; `[all]` gives every feature.
</details>

System dependencies (LaTeX engine + image tools):

```bash
# LaTeX dependencies (Ubuntu/Debian)
sudo apt-get install texlive-latex-extra latexdiff parallel imagemagick ghostscript

# LaTeX dependencies (macOS)
brew install texlive latexdiff parallel imagemagick ghostscript
```


## Problem

LaTeX compilation for scientific manuscripts is painful:

- **Environment inconsistency** — "It compiles on my machine" is not a solution when collaborating across Linux, macOS, WSL2, and HPC clusters.
- **Manual figure conversion** — Converting between PNG, SVG, PDF, Mermaid, and TIFF formats by hand wastes time and introduces errors.
- **No version tracking** — Generating tracked-change diffs between revisions requires manual `latexdiff` invocations and careful file management.
- **Fragmented tooling** — Separate workflows for compilation, bibliography management, table formatting, and submission packaging.
- **AI agents cannot help** — Without a programmatic interface, AI assistants have no way to compile or manage manuscripts.

## Solution

SciTeX Writer solves each of these problems:

- **Container-based reproducible compilation** — Consistent builds across all platforms via Docker, Singularity, or native installation with automatic engine selection (Tectonic, latexmk, or 3-pass).
- **Automatic asset conversion** — Figures and tables are converted in parallel from source formats (PNG, SVG, comma-separated values (CSV), Mermaid) to LaTeX-ready output.
- **Built-in version tracking with diff generation** — Every compilation archives the previous version and generates a `latexdiff` document automatically.
- **Unified interface** — One tool for compilation, bibliography deduplication, figure/table management, and arXiv export packaging.
- **44 Model Context Protocol (MCP) tools for AI agents** — AI assistants can compile, edit, and manage manuscripts programmatically.

## Architecture

```mermaid
flowchart TB
    subgraph Surfaces["Surfaces (user-facing)"]
        CLI["CLI<br/><code>_cli/</code>"]
        MCP["MCP Tools<br/><code>_mcp/</code>"]
        Web["Django Editor + Viewer<br/><code>_django/</code>"]
        Ports["Optional Bridges<br/><code>_ports/</code>"]
    end
    subgraph Engines["Engines (pure functions)"]
        Compile["Compile<br/><code>_compile/</code>"]
        Bib["Bibliography<br/><code>bib.py</code>"]
        Claim["Claims<br/><code>claim.py</code>"]
        Export["Export / arXiv<br/><code>export/</code>"]
        Migrate["Migration<br/><code>migration/</code>"]
    end
    subgraph Model["Project model (source of truth)"]
        DC["<code>_dataclasses/</code><br/>(immutable manuscript view)"]
        Proj["<code>_project/</code>"]
        Utils["<code>_utils/</code>"]
    end
    Surfaces --> Engines
    Engines --> Model
    Ports -.optional.-> Scholar["scitex-scholar<br/>(SCHOLAR_AVAILABLE)"]
    Ports -.optional.-> Figrecipe["figrecipe / clew / stats"]
```

<sub><b>Figure 4.</b> Layered architecture: surfaces delegate to engines, engines read the project model.</sub>

`scitex-writer` is layered in three concentric rings:

| Ring | Modules | Role |
|---|---|---|
| **Project model** | `_dataclasses/`, `_project/`, `_utils/` | Immutable view of a manuscript's tree, config, and contents — the source of truth every other layer reads. |
| **Engines** | `_compile/`, `bib.py`, `claim.py`, `export/`, `migration/` | Pure functions that operate on the project model — LaTeX compilation, BibTeX ops, claim rendering, arXiv export. No UI, no I/O assumptions beyond paths. |
| **Surfaces** | `_cli/`, `_mcp/`, `_django/`, `_ports/` | Four user-facing interfaces (CLI, MCP tools for AI agents, Django web editor, optional bridges to scitex-scholar/figrecipe/clew). Each delegates to the engines; they never bypass them. |

<sub><b>Table 1.</b> The three concentric rings of the codebase.</sub>

The `_django` editor + viewer ship the same code that runs locally and on `scitex.ai/apps/writer/` (no separate cloud-side implementation). Optional sibling integrations (`_ports/scholar.py`, etc.) follow the `*_AVAILABLE` flag pattern from `scitex-python` — if the peer isn't installed, the bridge degrades silently.

See [`Four Interfaces`](#four-interfaces) below for usage details per surface.

## Four Interfaces

| Interface | For | Description |
|-----------|-----|-------------|
| **Python API** | Human researchers | `import scitex_writer as sw` |
| **Command-Line Interface (CLI) Commands** | Terminal users | `scitex-writer compile`, `scitex-writer bib` |
| **MCP Tools** | AI agents | 44 tools for Claude/GPT integration |
| **Skills** | AI agent discovery | Workflow guides for capabilities and patterns |

<sub><b>Table 2.</b> The four user-facing interfaces.</sub>

<details open>
<summary><strong>Python API</strong></summary>

**Compile** — Build PDFs

```python
import scitex_writer as sw

sw.compile.manuscript("./my-paper")                    # Full compile
sw.compile.manuscript("./my-paper", draft=True)       # Fast draft mode
sw.compile.supplementary("./my-paper")
sw.compile.revision("./my-paper", track_changes=True)
```

**Export** — arXiv Submission

```python
sw.export.manuscript("./my-paper")                     # arXiv-ready tarball
sw.export.manuscript("./my-paper", output_dir="/tmp")  # Custom output dir
```

**Tables/Figures/Bib** — Create, Read, Update, Delete (CRUD) Operations

```python
# Tables
sw.tables.list("./my-paper")
sw.tables.add("./my-paper", "results", "a,b\n1,2", "Results summary")
sw.tables.remove("./my-paper", "results")

# Figures
sw.figures.list("./my-paper")
sw.figures.add("./my-paper", "fig01", "./plot.png", "My figure")
sw.figures.remove("./my-paper", "fig01")

# Bibliography
sw.bib.list_files("./my-paper")
sw.bib.add("./my-paper", "@article{Smith2024, title={...}}")
sw.bib.merge("./my-paper")  # Merge + deduplicate
```

**Guidelines** — Introduction, Methods, Results, and Discussion (IMRAD) Writing Tips

```python
sw.guidelines.get("abstract")
sw.guidelines.build("abstract", draft="Your draft...")
sw.guidelines.list_sections()  # ['abstract', 'introduction', 'methods', 'discussion', 'proofread']
```

**Prompts** — AI2 Asta

```python
from scitex_writer import generate_asta
result = generate_asta("./my-paper", search_type="related")
```

**GUI** — Browser-based Editor

```python
sw.gui("./my-paper")                              # Launch editor
sw.gui("./my-paper", port=8080, dark_mode=True)  # Custom options
```

</details>

<details>
<summary><strong>CLI Commands</strong></summary>

```bash
scitex-writer --help                           # Show all commands

# Compile - Build PDFs
scitex-writer compile manuscript               # Compile manuscript
scitex-writer compile manuscript --draft       # Fast single-pass
scitex-writer compile supplementary            # Compile supplementary
scitex-writer compile revision                 # Compile revision letter

# Export - arXiv submission
scitex-writer export manuscript               # Package for arXiv upload

# Checks - Pre-submission validation
scitex-writer check-references                 # Cross-refs, citations, labels, duplicate headings
scitex-writer check-limits                     # Section word limits + reference cap (config-driven)

# Update - Sync engine files from the template
scitex-writer update-project                   # Preview drifted engine files (safe; pass --yes to apply)

# Bibliography - Reference management
scitex-writer bib list-files                   # List .bib files
scitex-writer bib list-entries                 # List all entries
scitex-writer bib get Smith2024                # Get specific entry
scitex-writer bib add '@article{...}'          # Add entry
scitex-writer bib remove Smith2024             # Remove entry
scitex-writer bib merge                        # Merge and deduplicate

# Tables - CSV to LaTeX management
scitex-writer tables list                      # List tables
scitex-writer tables add results data.csv "Caption"
scitex-writer tables remove results

# Figures - Image management
scitex-writer figures list                     # List figures
scitex-writer figures add fig01 plot.png "Caption"
scitex-writer figures remove fig01

# Guidelines - IMRAD writing tips
scitex-writer guidelines list                  # List available sections
scitex-writer guidelines abstract              # Get abstract guidelines
scitex-writer guidelines abstract -d draft.tex # Build prompt with draft

# Prompts - AI2 Asta integration
scitex-writer prompts asta                     # Generate related papers prompt
scitex-writer prompts asta -t coauthors        # Find collaborators

# MCP server management
scitex-writer mcp list-tools                   # List all MCP tools (markdown)
scitex-writer mcp doctor                       # Check server health
scitex-writer mcp install                     # Show Claude Desktop config
scitex-writer mcp start                        # Start MCP server

# GUI - Browser-based editor
scitex-writer gui                              # Launch editor (current dir)
scitex-writer gui ./my-paper                   # Open specific project
scitex-writer gui --port 8080 --no-browser     # Custom port, no auto-open
```

</details>

<details>
<summary><strong>MCP Tools — 44 tools for AI Agents</strong></summary>

Turn AI agents into autonomous manuscript compilers.

| Category | Tools | Description |
|----------|-------|-------------|
| project | 4 | Clone, info, PDF paths, document types |
| compile | 4 | Manuscript, supplementary, revision, content |
| tables | 6 | CSV to LaTeX, list/add/remove, archive |
| figures | 6 | Convert, render PDF, list/add/remove, archive |
| bib | 6 | List files/entries, CRUD, merge/dedupe |
| guidelines | 3 | List, get, build with draft |
| prompts | 1 | AI2 Asta prompt generation |
| export | 1 | arXiv-ready tarball packaging |
| claim | 6 | Traceable scientific assertions |
| migration | 2 | Overleaf import/export |
| checks | 2 | Reference integrity, float order |
| skills | 2 | List and retrieve skill pages |
| update | 1 | Engine-file sync with drift detection |

<sub><b>Table 3.</b> MCP tool categories exposed to AI agents.</sub>

**Claude Desktop** (`~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "scitex-writer": {
      "command": "scitex-writer",
      "args": ["mcp", "start"]
    }
  }
}
```

> **[Full MCP tool reference](./docs/MCP_TOOLS.md)**

</details>

<details>
<summary><strong>Skills — for AI Agent Discovery</strong></summary>

<br>

Skills provide workflow-oriented guides that AI agents query to discover capabilities and usage patterns.

```bash
scitex-writer skills list              # List available skill pages
scitex-writer skills get SKILL         # Show main skill page
scitex-dev skills export --package scitex-writer  # Export to Claude Code
```

| Skill | Content |
|-------|---------|
| `quick-start` | Basic manuscript workflow |
| `compilation` | Compile manuscript, supplementary, revision |
| `bibliography` | BibTeX management, enrichment |
| `figures-and-tables` | Figure/table insertion and conversion |
| `claims` | Claim tracking and rendering |
| `cli-reference` | CLI commands |
| `mcp-tools` | MCP tools for AI agents |
| `writing-attitude` | Evidence requirements, scientific standards |
| `writing-figures-stats` | Figure rules, statistical reporting |
| `writing-proofreading` | Proofreading corrections, language rules |
| `writing-abstract` | Abstract template with 7-section structure |
| `writing-introduction` | Introduction template with 8-section structure |
| `writing-methods` | Methods template with reproducibility guidelines |
| `writing-discussion` | Discussion template with 5-section structure |
| `audit-paper` | Comprehensive pre-submission manuscript audit |

<sub><b>Table 4.</b> Bundled agent-facing skill pages.</sub>

</details>

<details>
<summary><strong>Additional Interfaces</strong></summary>

**Shell Scripts / Make** — Direct compilation without Python.

```bash
make manuscript              # Compile manuscript
make supplementary           # Compile supplementary
make revision                # Compile revision
make all                     # Compile all documents
make manuscript-export       # Package for arXiv submission
make clean                   # Remove build artifacts
./compile.sh manuscript --draft       # Fast single-pass
./compile.sh manuscript --no-figs     # Skip figures
./compile.sh manuscript --dark-mode   # Dark mode (Monaco theme)
./compile.sh manuscript --watch       # Hot-reload
SCITEX_WRITER_DARK_MODE=true make manuscript
```

**GUI Editor** — Standalone browser-based editor with file tree, PDF preview, and compilation controls.

<p align="center">
<p align="center">
  <img src="docs/demo-gui-light.png" alt="GUI Light Mode" width="380"/>
</p>
<sub><b>Figure 5.</b> Browser-based GUI editor, light mode.</sub>

<p align="center">
  <img src="docs/demo-gui-dark.png" alt="GUI Dark Mode" width="380"/>
</p>
<sub><b>Figure 6.</b> Browser-based GUI editor, dark mode.</sub>

```bash
uv pip install 'scitex-writer[all]'
scitex-writer gui                    # Current directory
scitex-writer gui ./my-paper         # Specific project
scitex-writer gui --port 8080        # Custom port
```

</details>

<details>
<summary><strong>Output Structure</strong></summary>

```
./scitex-writer/
├── 00_shared/                  # Shared resources across all documents
│   ├── title.tex / authors.tex / keywords.tex / journal_name.tex
│   ├── bib_files/              # Multiple .bib files (auto-merged and deduplicated)
│   ├── latex_styles/           # Common LaTeX configurations
│   └── templates/              # LaTeX document templates
├── 01_manuscript/              # Main manuscript
│   ├── contents/               # abstract, introduction, methods, results, discussion
│   │   ├── figures/            # Figure captions + media
│   │   └── tables/             # Table captions + CSV data
│   ├── archive/                # Version history (gitignored)
│   ├── manuscript.tex          # Compiled LaTeX
│   ├── manuscript_diff.tex     # Change-tracked version
│   └── manuscript.pdf          # Output PDF
├── 02_supplementary/           # Supplementary materials (same structure)
├── 03_revision/                # Revision response letter
│   └── contents/               # editor/, reviewer1/, reviewer2/
├── config/                     # config_manuscript.yaml
└── scripts/                    # containers, installation, shell, python
```

</details>

## Part of SciTeX

`scitex-writer` is part of [**SciTeX**](https://scitex.ai). Install via
the umbrella with `pip install scitex[writer]` to use as
`scitex.writer` (Python) or `scitex writer ...` (CLI).

>Four Freedoms for Research
>
>0. The freedom to **run** your research anywhere — your machine, your terms.
>1. The freedom to **study** how every step works — from raw data to final manuscript.
>2. The freedom to **redistribute** your workflows, not just your papers.
>3. The freedom to **modify** any module and share improvements with the community.
>
>AGPL-3.0 — because we believe research infrastructure deserves the same freedoms as the software it runs on.

## Features

<details>
<summary><strong>Details</strong></summary>

| Feature                | Description                                                           |
|------------------------|-----------------------------------------------------------------------|
| **Separated Files**    | Modular sections (abstract, intro, methods, results, discussion)      |
| **Built-in Templates** | Pre-configured manuscript, supplementary materials, and revision      |
| **Bibliography**       | Multi-file with auto-deduplication, 20+ citation styles               |
| **Assets**             | Parallel figure/table processing (PNG, PDF, SVG, Mermaid, CSV)        |
| **GUI Editor**         | Browser-based editor with PDF preview (`scitex-writer gui`)           |
| **Dark Mode**          | Monaco/VS Code dark theme for comfortable reading (`--dark-mode`)     |
| **Section Limits**     | Word caps per IMRAD section + reference cap, checked before compile    |
| **Multi-Engine**       | Auto-selects best engine (Tectonic 1-3s, latexmk 3-6s, 3-pass 12-18s) |
| **Cross-Platform**     | Linux, macOS, WSL2, Docker, Singularity, HPC clusters                 |

<sub><b>Table 5.</b> Feature summary.</sub>

</details>

## Usage

<details>
<summary><strong>PDF Compilation</strong></summary>

```bash
# Basic compilation
./scripts/shell/compile_manuscript.sh          # Manuscript
./scripts/shell/compile_supplementary.sh       # Supplementary
./scripts/shell/compile_revision.sh            # Revision letter

# Performance options
./scripts/shell/compile_manuscript.sh --draft      # Fast single-pass
./scripts/shell/compile_manuscript.sh --no-figs    # Skip figures
./scripts/shell/compile_manuscript.sh --no-tables  # Skip tables
./scripts/shell/compile_manuscript.sh --no-diff    # Skip diff generation

# Engine selection
./scripts/shell/compile_manuscript.sh --engine tectonic  # Fastest
./scripts/shell/compile_manuscript.sh --engine latexmk   # Standard
./scripts/shell/compile_manuscript.sh --engine 3pass     # Most compatible

# Development
./scripts/shell/compile_manuscript.sh --watch  # Hot-reload on file changes
./scripts/shell/compile_manuscript.sh --clean  # Remove cache
```

</details>

<details>
<summary><strong>Figures</strong></summary>

1. Place media files in `01_manuscript/contents/figures/caption_and_media/`:
   ```
   01_example_figure.png
   01_example_figure.tex  # Caption file
   ```

2. Caption file format (`01_example_figure.tex`):
   ```latex
   %% Figure caption
   \caption{Your figure caption here. Explain panels (A, B, C) if applicable.}
   \label{fig:example_figure_01}
   ```

3. Supported formats: PNG, JPEG, PDF, SVG, TIFF, Mermaid (.mmd)

4. Figures auto-compile and include in `FINAL.tex`

</details>

<details>
<summary><strong>Tables</strong></summary>

1. Place CSV + caption in `01_manuscript/contents/tables/caption_and_media/`:
   ```
   01_example_table.csv
   01_example_table.tex  # Caption file
   ```

2. CSV auto-converts to LaTeX table format

3. Caption file format (`01_example_table.tex`):
   ```latex
   %% Table caption
   \caption{Your table caption. Define abbreviations used.}
   \label{tab:example_table_01}
   ```

</details>

<details>
<summary><strong>References</strong></summary>

Organize references in multiple `.bib` files - they auto-merge with deduplication:

```bash
00_shared/bib_files/
├── methods_refs.bib      # Method-related references
├── field_background.bib  # Background literature
└── my_papers.bib         # Your own publications
```

Change citation style in `config/config_manuscript.yaml`:
- `unsrtnat` (numbered, order of citation)
- `plainnat` (numbered, alphabetical)
- `apalike` (author-year, APA style)
- `IEEEtran` (IEEE format)
- `naturemag` (Nature style)

</details>

## Documentation

<details>
<summary><strong>Details</strong></summary>

| Guide | Description |
|-------|-------------|
| [Installation](docs/01_GUIDE_INSTALLATION.md) | Setup for all environments |
| [Quick Start](docs/01_GUIDE_QUICK_START.md) | Common workflows |
| [Content Creation](docs/01_GUIDE_CONTENT_CREATION.md) | Writing manuscripts |
| [Bibliography](docs/01_GUIDE_BIBLIOGRAPHY.md) | Reference management |
| [Architecture](docs/02_ARCHITECTURE_IMPLEMENTATION.md) | Technical details |

<sub><b>Table 6.</b> Documentation guide index.</sub>

</details>

---

<p align="center">
  <a href="https://scitex.ai" target="_blank"><img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40"/></a>
  <br>
  AGPL-3.0
</p>

<!-- EOF -->

# SciTeX Writer MCP Tools (44 total)

Model Context Protocol tools for AI agent integration.

```bash
scitex-writer mcp list-tools    # List all tools
scitex-writer mcp start         # Start MCP server (stdio)
scitex-writer mcp doctor        # Health check
scitex-writer mcp install       # Show Claude Desktop config guide
```

## Tools by Module

### bib (6 tools)
| Tool | Description |
|------|-------------|
| `writer_add_bibentry` | Add a BibTeX entry to a bibliography file |
| `writer_get_bibentry` | Get a specific BibTeX entry by citation key |
| `writer_list_bibentries` | List all BibTeX entries in the project |
| `writer_list_bibfiles` | List all bibliography files in the project |
| `writer_merge_bibfiles` | Merge all .bib files into one, with deduplication |
| `writer_remove_bibentry` | Remove a BibTeX entry by citation key |

### checks (2 tools)
| Tool | Description |
|------|-------------|
| `writer_checks_references` | Check all LaTeX `\ref{}` / `\cite{}` resolve correctly |
| `writer_checks_float_order` | Audit float (figure/table) numbering order |

### claim (7 tools)
| Tool | Description |
|------|-------------|
| `writer_claim_add` | Register a claim in the scitex-clew store (statistic, value, citation, figure, table); optional source_keys/tolerance for the value-vs-source check |
| `writer_claim_format` | Render a claim as a formatted string (nature/apa/plain style) |
| `writer_claim_get` | Get details for a single claim |
| `writer_claim_list` | List all claims with clew status, provenance pointers and previews |
| `writer_claim_remove` | Retire a claim (clew supersede; kept for audit) |
| `writer_claim_render` | Generate claims_rendered.tex from the clew store for LaTeX compilation |
| `writer_claim_check_values` | Re-read located claim values from their source files and report mismatches |

### compile (4 tools)
| Tool | Description |
|------|-------------|
| `writer_compile_content` | Compile raw LaTeX content to PDF with color modes |
| `writer_compile_manuscript` | Compile manuscript LaTeX document to PDF |
| `writer_compile_revision` | Compile revision document to PDF with change tracking |
| `writer_compile_supplementary` | Compile supplementary materials to PDF |

### export (1 tool)
| Tool | Description |
|------|-------------|
| `writer_export_manuscript` | Export manuscript for arXiv submission |

### figures (6 tools)
| Tool | Description |
|------|-------------|
| `writer_add_figure` | Add a figure (copy image + create caption) |
| `writer_figures_archive` | Move a figure to legacy/ instead of deleting |
| `writer_figures_convert` | Convert figure between formats (e.g., PDF to PNG) |
| `writer_figures_list` | List all figures in a writer project |
| `writer_figures_pdf_to_images` | Render PDF pages as images |
| `writer_figures_remove` | Remove a figure (image + caption) |

### guidelines (3 tools)
| Tool | Description |
|------|-------------|
| `writer_guideline_build` | Build editing prompt by combining guideline with draft |
| `writer_guideline_get` | Get IMRAD writing guideline for a manuscript section |
| `writer_guideline_list` | List available IMRAD writing guideline sections |

### migration (2 tools)
| Tool | Description |
|------|-------------|
| `writer_migration_from_overleaf` | Import an Overleaf ZIP into a scitex-writer project |
| `writer_migration_to_overleaf` | Export a scitex-writer project as an Overleaf-compatible ZIP |

### project (4 tools)
| Tool | Description |
|------|-------------|
| `writer_clone_project` | Create a new LaTeX manuscript project from template |
| `writer_get_pdf` | Get path to compiled PDF for a document type |
| `writer_get_project_info` | Get writer project structure and status |
| `writer_list_document_types` | List available document types in a writer project |

### prompts (1 tool)
| Tool | Description |
|------|-------------|
| `writer_prompts_asta` | Generate AI2 Asta prompt for finding related papers |

### skills (2 tools)
| Tool | Description |
|------|-------------|
| `writer_skills_list` | List available skill pages |
| `writer_skills_get` | Get the content of a specific skill page |

### tables (6 tools)
| Tool | Description |
|------|-------------|
| `writer_add_table` | Add a new table (CSV + caption) to the project |
| `writer_csv_to_latex` | Convert CSV file to LaTeX table format |
| `writer_latex_to_csv` | Convert LaTeX table to CSV format |
| `writer_list_tables` | List all tables in a writer project |
| `writer_remove_table` | Remove a table (CSV + caption) from the project |
| `writer_tables_archive` | Move a table to legacy/ instead of deleting |

### update (1 tool)
| Tool | Description |
|------|-------------|
| `writer_update_project` | Update engine files from upstream template, preserving user content |

## Claude Desktop Configuration

Add to `~/.config/Claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

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

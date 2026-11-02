---
name: scitex-writer
description: |
  [WHAT] End-to-end LaTeX manuscript toolchain — 44 MCP tools — project (clone/info/get_pdf), compile (manuscript / supplementary / revision with tracked changes), BibTeX (add/list/get/remove/merge, dedup by DOI), figures + tables (add/list/remove/archive, csv_to_latex, pdf_to_images), claims (`\vclaim{}` linked to scitex-clew session hashes for verifiable assertions), checks (float order, references), export + Overleaf migration, per-journal guidelines, AI2 Asta prompts.
  [WHEN] Use whenever the user asks to compile manuscript / build PDF / supplementary / revision with tracked changes, add figure/table/bibentry, merge or dedup bibliography, or diagnose the mounted Writer editor.
  [HOW] `pip install scitex-writer` then `import scitex_writer`; see leaf skills for details.
tags: [scitex-writer]
allowed-tools: mcp__scitex__writer_*
primary_interface: mixed
interfaces:
  python: 1
  cli: 3
  mcp: 3
  skills: 2
  http: 0
---

# scitex-writer

LaTeX manuscript compilation framework. Compiles manuscripts,
supplementary materials, and revisions with tracked changes. Manages
bibliography (BibTeX merge, DOI dedup), figures/tables (auto-discovery,
CSV-to-LaTeX), and verifiable claims linked to session hashes.

## Install & import

`pip install scitex-writer` gives `import scitex_writer as sw`. Also
`pip install scitex` to get `import scitex.writer as sw`. See
[../../general/02_interface-python-api.md].

## Sub-skills

### Mandatory leaves
- [01_installation.md](01_installation.md) — pip install + extras + smoke verify
- [02_quick-start.md](02_quick-start.md) — clone-and-compile minimal example
- [03_python-api.md](03_python-api.md) — top-level Python surface
- [04_cli-reference.md](04_cli-reference.md) — `scitex-writer` subcommand summary
- [05_mcp-tools.md](05_mcp-tools.md) — MCP tools for AI agents

### Core / interfaces
- [06_quick-start.md](06_quick-start.md) — basic workflow
- [07_cli-reference.md](07_cli-reference.md) — CLI reference (legacy detail)

## Workflows

- [10_compilation.md](10_compilation.md) — compile manuscript/supp/revision
- [11_bibliography.md](11_bibliography.md) — BibTeX add/merge/dedup
- [12_figures-and-tables.md](12_figures-and-tables.md) — figure/table lifecycle
- [13_claims.md](13_claims.md) — verifiable `\vclaim{}` with session hash
- [14_manuscript-workflow.md](14_manuscript-workflow.md) — end-to-end workflow
- [15_audit-paper.md](15_audit-paper.md) — pre-submission audit: cross-refs + tables
- [16_audit-paper-figures-data.md](16_audit-paper-figures-data.md) — audit: figures, variables, data
- [17_audit-paper-methods-output.md](17_audit-paper-methods-output.md) — audit: methods, structure, cross-doc, pitfalls
- [18_mounted-editor.md](18_mounted-editor.md) — mounted GUI project context, presence, preview rail, and interaction checks

## Scientific writing standards

- [21_writing-proofreading.md](21_writing-proofreading.md) — language rules, corrections, section-specific
- [22_writing-figures-stats.md](22_writing-figures-stats.md) — figure rules, stats reporting
- [23_writing-mermaid.md](23_writing-mermaid.md) — academic mermaid style
- [24_writing-proofreading-style.md](24_writing-proofreading-style.md) — tone, hedging, transitions, anti-patterns
- [25_writing-attitude.md](25_writing-attitude.md) — evidence, critical analysis
- [26_writing-during-exploration.md](26_writing-during-exploration.md) — discipline for in-flight manuscripts: `\vclaim{}` for confirmed numbers, `\placeholder{}`/`\ph{}` for WIP prose, `\hlref{XXX}` for missing refs, v0/pilot vs final/structurally-masked disclosure rules, claim-type pitfall (text→silently dropped; use value), pre-submission grep gate.

## Section templates

- [30_writing-abstract.md](30_writing-abstract.md) — 7-section abstract
- [31_writing-introduction.md](31_writing-introduction.md) — 8-section introduction template
- [32_writing-methods.md](32_writing-methods.md) — reproducibility-focused methods
- [33_writing-discussion.md](33_writing-discussion.md) — 5-section discussion template
- [34_writing-introduction-example.md](34_writing-introduction-example.md) — intro section tags + example
- [35_writing-discussion-example.md](35_writing-discussion-example.md) — discussion section tags + example


## Environment

- [20_env-vars.md](20_env-vars.md) — SCITEX_* env vars read by scitex-writer at runtime

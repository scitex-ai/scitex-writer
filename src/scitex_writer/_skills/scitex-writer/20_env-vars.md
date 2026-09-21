---
description: |
  [TOPIC] scitex-writer — Environment Variables
  [DETAILS] Environment variables read by scitex-writer at import / runtime. Follow SCITEX_<MODULE>_* convention — see general/10_arch-environment-variables.md..
tags: [scitex-writer-env-vars]
---

# scitex-writer — Environment Variables

## Paths & output

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_WRITER_ROOT` | Root directory for manuscript projects. | `~/proj` | path |
| `SCITEX_WORKING_DIR` | Current working project directory (overrides `SCITEX_WRITER_ROOT`). | `$PWD` | path |
| `SCITEX_WRITER_GUIDELINE_DIR` | Directory with custom writing-guideline YAMLs. | bundled | path |
| `SCITEX_WRITER_PROMPT_DIR` | Directory with custom LLM prompt templates. | bundled | path |

## Compilation

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_WRITER_ENGINE` | LaTeX engine (`pdflatex`, `xelatex`, `lualatex`). | `pdflatex` | string |
| `SCITEX_WRITER_DRAFT_MODE` | Render manuscript in draft mode (faster, no figures). | `false` | bool |
| `SCITEX_WRITER_DARK_MODE` | Render PDF with dark page + light text (preview only; equivalent to the `-dm`/`--dark-mode` flag and `theme: dark` config). Does NOT adapt figures — they stay light, so use light mode for submission. | `false` | bool |
| `SCITEX_WRITER_VERBOSE_PDFLATEX` | Forward full pdflatex output to stderr. | `false` | bool |
| `SCITEX_WRITER_VERBOSE_BIBTEX` | Forward full bibtex output to stderr. | `false` | bool |
| `SCITEX_STYLE` | Citation / style override (shared with scitex-plt). | `default` | string |

## Pre-compile / post-compile checks (severity)

Each check resolves a severity; precedence is the CLI flag > the env var below >
project `./config.yaml` > user `~/.scitex/writer/config.yaml` > the per-check
default. Setting `off` disables a check; `warn` reports but exits 0; `error`
exits non-zero.

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_WRITER_LINT_STRICT` | Tighten `check-limits` + `check-overflow` warnings to errors (the legacy strict toggle). Scoped to those two checks only. | `false` | bool |
| `SCITEX_WRITER_LIMITS` | Severity for the word/reference-limit check (`off`/`warn`/`error`). Default `warn`; `--strict`/`limits.strict` tighten to `error`. | `warn` | enum |
| `SCITEX_WRITER_OVERFLOW` | Severity for the off-page overflow check (`off`/`warn`/`error`). Default `warn`; `--strict`/`overflow.strict` tighten to `error`. | `warn` | enum |
| `SCITEX_WRITER_PAPER_SYMLINK` | Severity for the `paper -> .scitex/writer` symlink check (`off`/`warn`/`error`/`repair`). Private convention — default `warn`. | `warn` | enum |
| `SCITEX_WRITER_MEDIA_PROVENANCE` | Severity for the media-symlink/provenance check on `caption_and_media/` (`off`/`warn`/`error`). Private convention — default `off`. | `off` | enum |
| `SCITEX_WRITER_REFERENCES` | Severity for the cross-reference/citation/label check (`off`/`warn`/`error`). Default `error` (a broken `\ref`/`\cite` is a real defect); `warn` reports but exits 0; `off` disables. | `error` | enum |
| `SCITEX_WRITER_FLOAT_ORDER` | Severity for the figure/table reference-order check (`off`/`warn`/`error`). Default `error`. `--level` governs only the gating exit; `--fix`/`--dry-run` always run regardless of level. | `error` | enum |
| `SCITEX_WRITER_CAPTION_FOOTNOTE` | Severity for the `\footnote`-in-`\caption{}` lint (`off`/`warn`/`error`). Default `error`. | `error` | enum |
| `SCITEX_WRITER_REF_INTEGRITY` | Severity for the pre-compile reference-integrity gate (`off`/`warn`/`error`). Default `error`. | `error` | enum |
| `SCITEX_WRITER_TABLE_DECIMALS` | Severity for the table decimal-consistency safety-net lint (`off`/`warn`/`error`). Reads the COMPILED table `.tex` and warns when a numeric column's cells disagree on decimal places. Companion to the PR #185 auto-pad (which only normalizes the pandas backend); catches the `csv2latex`/AWK backends + hand-authored tables the auto-pad misses. Default `warn` (never blocks by default; the auto-pad is the systemic prevention). | `warn` | enum |
| `SCITEX_WRITER_CLEW_VERIFY` | Severity for the pre-compile clew provenance gate — re-verifies every clew-registered claim against its bound source (`off`/`warn`/`error`). Default `error` for **research** projects (`.scitex/dev/config.yaml` `project-type: research`), `off` otherwise. NO_CLAIMS and a missing `clew` CLI warn (never block) unless `clew_verify.require_claims` is set. `clew_verify.strict` / `--strict` forwards `--strict` to clew; `clew_verify.require_claims` / `--require-claims` makes NO_CLAIMS + missing-clew hard-fail at the resolved level (ADR-0021). | `error` (research) / `off` | enum |
| `SCITEX_WRITER_CLEW_BIN` | Path to the `clew` executable used by the provenance gate. Defaults to `clew` on `PATH`. | `clew` | path |
| `SCITEX_WRITER_CLEW_PRESENTATION` | Primary ON/OFF switch for the page-1 clew *presentation* layer (marks/badge/legend/explainer/signature), resolved pre-compile by `render_clew_toggles.py`. `on`/`true`/`yes` enables the full co-author-facing set; `off` disables all. Overrides the project `.scitex/writer/config.yaml` `clew_presentation` key (which may instead be a per-toggle mapping — see below). Default off. | `off` | enum |

> **`clew_presentation` toggle set** (config-mapping keys under
> `.scitex/writer/config.yaml` `clew_presentation:`, each `true`/`false`,
> absent = off). The env primary `SCITEX_WRITER_CLEW_PRESENTATION=on` enables
> the **primary set** (`markers`, `badge`, `legend`, `explainer`, `signature`);
> `attest` and `legend_first` are **opt-in only** (never enabled by primary-on).
>
> | key | effect |
> |---|---|
> | `markers` | verdict-colored wavy underlines on `\clewval`/`\clewmark`/`\clewcite`/`\clewfig` |
> | `badge` | "Clew Verified" stamp auto-placed at page-1 top |
> | `legend` | status-color key auto-placed at end-of-doc |
> | `explainer` | "How to read provenance marks" box (author-placed via `\clewExplainer`) |
> | `signature` | "Compiled by SciTeX Writer." colophon at end-of-doc |
> | `attest` | "Provenance audited by SciTeX Clew" line at end-of-doc (opt-in) |
> | `legend_first` | auto-emit the status-color key at the **top of page 1** (opt-in; independent of `legend`, excluded from the primary set so it never double-renders) |
| `SCITEX_WRITER_COMPILE_ARTIFACTS` | Severity for the POST-compile verification gate (`off`/`warn`/`error`). Default `error`. Fails loud when the compiled `.tex` references `\includegraphics` (N>0) but the PDF embeds 0 images (silent figure miss), plus secondary log deficiency signals. PDF embedding check needs poppler (`pdfimages`); skipped-with-warning when absent. | `error` | enum |
| `SCITEX_WRITER_VERSION_FRESHNESS` | Severity for the pre-compile version-freshness gate (`off`/`warn`/`error`). Default `error`. Fails loud when the vendored engine (stamped in `00_shared/.scitex-writer-vendored-version` by `update-project`) is behind the installed scitex-writer — re-vendor with `scitex-writer update-project`. Absent stamp or no installed pkg → warn (never blocks). | `error` | enum |

> **`references` vs `ref_integrity` are separate knobs.** `references` is the
> advisory cross-reference/citation/label *report*; `ref_integrity` is the
> *pre-compile integrity gate*. Downgrading `references` (e.g. to `off`) does
> **not** disable `ref_integrity`, so a broken `\ref` can still block a compile
> via the gate — defense in depth by design.

## Branding & naming

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_WRITER_ALIAS` | CLI alias name used in help text. | `scitex writer` | string |
| `SCITEX_WRITER_BRAND` | Branding token injected into templates. | `SciTeX` | string |

## Guidelines / Asta prompts

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_WRITER_GUIDELINE_ABSTRACT` | Override path for the abstract guideline YAML. | bundled | path |
| `SCITEX_WRITER_PROMPT_ASTA_COAUTHORS` | Asta coauthors-prompt override path. | bundled | path |
| `SCITEX_WRITER_PROMPT_ASTA_RELATED` | Asta related-work prompt override path. | bundled | path |

## Cross-package

| Variable | Owner | Purpose |
|---|---|---|
| `SCITEX_UI_STATIC` | scitex-ui | Static-asset path used when embedding figures produced by the UI pipeline. |

## Feature flags

- **opt-in:** `SCITEX_WRITER_DRAFT_MODE=true`, `SCITEX_WRITER_DARK_MODE=true`,
  `SCITEX_WRITER_VERBOSE_PDFLATEX=true`, `SCITEX_WRITER_VERBOSE_BIBTEX=true`
  — all off by default to keep production compilation clean.
- No opt-out flags.

## Audit

```bash
grep -rhoE 'SCITEX_[A-Z0-9_]+' $HOME/proj/scitex-writer/src/ | sort -u
```

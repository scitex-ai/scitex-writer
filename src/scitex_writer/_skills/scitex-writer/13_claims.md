---
description: |
  [TOPIC] Claims
  [DETAILS] Verifiable claims — registered in the scitex-clew store (one claim store), rendered as \vclaim, value-checked against their source before every compile.
tags: [scitex-writer-claims]
---

# Claims

Claims are verifiable statements linked to evidence (data, figures, statistics).
Every claim is registered with **scitex-clew** — the single claim store — so a
`\vclaim{id}` back-traces through clew's DAG to the recorded
input -> executable -> output that produced it.

## Storage (one store, no fallback)

- `writer_claim_add` / `sw.claim.add` call `scitex_clew.add_claim(claim_id=<id>,
  file_path=<tex with the \vclaim call site>, line_number,
  claim_value=<rendered display string>, source_file=<output_file>,
  source_session=<session_id>, value=<the located fields>, source_keys,
  tolerance, metadata={"schema": "scitex-writer-claim/2", type, value,
  context, test}, project_root=<project>)` — clew's native columns, so
  `clew verify` (and live-paper's clew evidence provider) re-reads every
  located value itself. Rows written by writer < 2.44 (all fields packed in
  `claim_value` as `scitex-writer-claim/1` JSON) are still read.
- Every clew call is scoped by `project_root`; the working directory is never
  changed, so one process can serve many projects.
- A claim without `source_keys` is allowed: clew shows it as "registered, not
  checkable" (it tries to find the stated number in the source; ambiguous or
  absent -> unchecked, never passed).
- `00_shared/claims.json` is a **derived export** of the store
  (`"_derived_from": "scitex-clew"`), regenerated after every change. Do not
  edit it; edits are overwritten (the store wins, with a warning).
- A **legacy** writer-owned `claims.json` is migrated into clew on first read,
  loudly (WARN log + `notices`); the original is kept as
  `00_shared/claims.json.pre-clew`.
- No scitex-clew, or store unreachable (`SCITEX_STORE_DSN`): every claim call
  returns `success: False, error_kind: "clew_unavailable"`, and the compile's
  Claims Render step aborts. There is **no** local-JSON fallback.
- Remove = clew `supersede_claim` (audit trail kept; re-adding the same id
  makes it active again).
- `output_hash`, if given, must match the file's current SHA-256, else the
  claim is refused (the value came from another version of the file).

## Value-vs-source check

A hash proves the source file is unchanged; it cannot prove the manuscript
number was copied from it correctly. Record WHERE each value lives:

```python
sw.claim.add(
    "./paper", "auc", "value", {"value": 0.91},
    output_file="results/metrics.json",
    source_keys={"value": {"pointer": "/test/auc"}},       # json/yaml: RFC 6901
)
sw.claim.add(
    "./paper", "s02_acc", "value", {"value": 0.83},
    output_file="results/per_subject.csv",
    source_keys={"value": {"row": {"subject": "S02"}, "column": "acc"}},  # csv/tsv
    tolerance={"abs_tol": 0.005},                           # optional
)
```

- Keys of `source_keys` are fields of the claim `value` dict (`"."` = a bare
  scalar value). A string locator is shorthand for `{"pointer": ...}`.
  `row` is a 0-based int or a `{column: value}` selector matching exactly one row.
- Tolerance: per-locator `abs_tol`/`rel_tol` > claim-level `tolerance` >
  implied by the written precision (`0.91` -> ±0.005). Strings compare exactly.
- A claim that already disagrees with its source is refused at registration.
- Before every compile, `scripts/python/check_claim_values.py` (in
  `run_provenance_checks.sh`) re-reads every located value and fails on a
  mismatch. Level `claim_values` (`--level`, `SCITEX_WRITER_CLAIM_VALUES`,
  `config.yaml`), default `error`. Claims without `source_keys` are listed as
  unchecked, never as passed.

## Claim positions in the PDF

Every compile writes `<pdf stem>.pdf-anchors.json` beside the PDF (e.g.
`01_manuscript/manuscript.pdf-anchors.json`), the file a Live Paper reader uses
to box each claim:

```json
{"schema": "scitex-writer.pdf-anchors/v1", "pdf": "manuscript.pdf",
 "pdf_sha256": "<sha256 of the PDF bytes>",
 "anchors": {"acc_mean": {"page": 3, "bbox": [x0, y0, x1, y1],
                          "rects": [{"page": 3, "bbox": [...]}],
                          "occurrences": [{"page": 3, "bbox": [...]}]}}}
```

- `page` is 1-based; boxes are PDF points from the bottom-left page corner.
- `rects` has one box per line of a claim that wraps (also across a page or
  column break); `bbox` is their union on the page where the claim starts.
- A claim printed more than once is anchored at its first place in reading
  order; `occurrences` lists them all.
- `\vclaim` records the positions in the `.aux`
  (`scripts/python/emit_claim_anchors.py` reads them). Copy the file with the
  PDF; a reader ignores it when `pdf_sha256` does not match the PDF.

## MCP Tools

| Tool | Description |
|------|-------------|
| `writer_claim_add` | Register a claim in the clew store (`source_keys`, `tolerance`, `tex_file`, `line_number` optional) |
| `writer_claim_get` | Get claim by ID |
| `writer_claim_list` | List all claims (with clew status + provenance pointers) |
| `writer_claim_remove` | Retire a claim (clew supersede) |
| `writer_claim_render` | Render claims to LaTeX (`claims_rendered.tex`) from the store |
| `writer_claim_format` | Format claim for display |
| `writer_claim_check_values` | Re-read located values from their sources and compare |

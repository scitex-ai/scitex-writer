---
description: |
  [TOPIC] Writing a manuscript while data is still evolving (exploratory phase)
  [DETAILS] Discipline for distinguishing "confirmed numbers" (use `\vclaim{}`), "in-flight prose to be replaced" (use `\placeholder{}` / `\ph{}`), "missing citations" (use `\hlref{XXX}`), and "v0 / pilot / honor-system" data versus final / structurally-masked data. Includes claim-type pitfalls (text claims silently dropped — use value), forward-vs-past tense rules for unfinished work, the pre-submission grep gate, and the "lessons learned 2026-05-05" appendix from the paper-scitex-clew cohort A v0 fleet runs.
tags: [scitex-writer-writing-during-exploration]
---

# Writing during exploration

A manuscript-in-progress always carries three kinds of incomplete content:

1. **Numbers that will change** as experiments rerun — keep the prose
   stable, swap the values automatically.
2. **Prose that needs human revision** — flag visibly, never let it
   slip into a submission.
3. **Citations that you mean to add** — flag inline, fill from
   crossref/scholar later.

The toolchain provides a distinct mechanism for each. Use them
deliberately so submission-readiness is mechanically checkable.

## The three placeholder mechanisms

| Concern | Macro | Behaviour |
|---|---|---|
| Confirmed number from a registered claim | `\vclaim{<id>}` | resolves at compile-time from the scitex-clew claim store (a registered, SHA-256-anchored value; `00_shared/claims.json` is only its derived export); compile fails / `[claim:<id>]` renders if unresolved |
| Prose / sentence not yet finalised | `\placeholder{...}` (alias `\ph{...}`) | red bold on yellow background in PDF — visually obvious; survives compile but flags the issue |
| Reference (paper, table, figure) you intend to add later | `\hlref{XXX}` | renders highlighted; resolves only when you replace it with the real `\citep{}` / `\ref{}` |

**Rule of choice.** Use `\vclaim{}` when the answer is "the verified
number"; `\placeholder{}` when the answer is "real prose I haven't
written yet"; `\hlref{}` when the answer is "a citation I'll look up
later".

## Claim discipline

Register every reportable number, even draft ones, via
`scripts/register_claims.py` (or the `sw.claim.add()` API). Once
registered:

- Use `\vclaim{<id>}` everywhere in the manuscript.
- Re-running `register_claims.py` after experiments updates the value
  in one place; the manuscript follows automatically.
- Pre-submission, every `\vclaim{}` is grep-able and traceable to a
  source file and SHA-256 hash.
- Pass `output_file=` plus `source_keys=` (JSON Pointer / csv cell) so the
  pre-compile `claim_values` check re-reads the number from its source and
  fails the build if they drift apart (see 13_claims.md).

### Claim-type pitfall

`sw.claim.add()` accepts `claim_type` ∈ {`value`, `statistic`,
`text`, …}. **`text` is not a writer claim type** (writer's types are
`statistic`, `value`, `citation`, `figure`, `table`); older versions
dropped such claims silently, current ones return `success: False` — check
the return value. Symptom: the manuscript shows
`[claim:<id>]` even though `register_claims.py` reported the claim
was added.

**Fix**: register string-valued or range-string claims as `value`
type, not `text`. Format the value as a string yourself
(`f"{lo:.2f}--{hi:.2f}"`) and register with `claim_type="value"`.
Lesson learned 2026-05-05 from the paper-scitex-clew session
(`session_overhead_ranges`, `bm198_overhead_ranges`,
`session_inner_cost_range_ms`, `crossref_n_records` all initially
broken with `text`; switched to `value` and they rendered cleanly).

## v0 / pilot vs final / structurally-masked data

Manuscripts in flight often have data from multiple regimes:

- **v0 / pilot** — early run, possibly under honor-system masking,
  not the canonical numbers.
- **final** — the masking-strict, oracle-isolated, audit-trailed run
  intended for submission.

Disclose explicitly in prose. Never let the reader think a v0 number
was structurally masked. Recommended phrasings:

| Regime | Phrasing |
|---|---|
| v0 fleet, honor-system masking | "the v0 fleet runs (N score.json files preserved on `<host>`) used **honor-system** oracle masking; the final rerun replaces this with structural masking (third-party CI verifier on GitHub Actions)" |
| Data staged but not run | "the dataset finished staging on `<date>` and is **awaiting** a SLURM array under the structurally-masked verifier, so cohort X **contributes no headline numbers** to this submission" |
| Pilot capsule for an unrun cohort | "a pilot agent on `<host>` (`<model>`, `<settings>`) reproduces the four-stage pipeline end-to-end without seeing the oracle, demonstrating that the same framework supports a fleet of automated translators" |

These are forward-looking framings. They keep the prose honest while
the pipeline matures.

### Tense rule

| Status | Tense |
|---|---|
| Dataset staged but no runs yet | future / "is queued / staged / awaiting" |
| Pilot run completed under v0 masking | past + caveat ("v0 / honor-system; final rerun planned") |
| Full structurally-masked run completed | past, plain |

Avoid *"we exercise the playbook across N cohorts"* unless **all N**
have been exercised. Otherwise: *"we apply the playbook to N cohorts:
A is in pilot run; B and C are staged"*.

## Pre-submission grep gate

Before any submission, run:

```bash
# 1. No unresolved claim placeholders (vclaim resolution failure)
pdftotext paper/01_manuscript/manuscript.pdf - \
  | grep -oE '\[claim:[a-z_]+\]' | sort -u
# Should be empty.

# 2. No \placeholder{...} survivors in the source
grep -rE '\\\\placeholder\{|\\\\ph\{' paper/01_manuscript/contents/*.tex \
  | grep -v '%%'
# Should be empty (or only inside literal example blocks).

# 3. No \hlref{...} unresolved citations
grep -rE '\\\\hlref\{' paper/01_manuscript/contents/*.tex
# Should be empty.

# 4. No "v0" "honor-system" "pilot" "queued" marker words in
#    Results headline numbers (only in dedicated transparency
#    paragraphs is OK)
grep -nE 'v0|honor.system|pilot|queued' paper/01_manuscript/contents/results.tex
# Review every match; ensure each is properly framed.
```

This is the same gate as a CI check — wire it into the manuscript's
pre-submission Makefile target if practical.

## Recommended workflow during exploration

1. **Draft the prose first.** Write the manuscript narrative with
   placeholders (`\placeholder{}`, `\ph{}`) where the data isn't in
   yet. Don't wait for runs to finish before writing.
2. **Register claims as runs land.** Each registered claim becomes a
   `\vclaim{}` in the prose; replace `\placeholder{}` instances.
3. **Disclose v0 vs final inline.** When v0 numbers fill a slot, add
   a one-sentence transparency paragraph (Results §3.X "preliminary;
   under honor-system masking; structural-masking rerun pending").
4. **Pre-submit grep gate.** Run the four checks above. Zero
   unresolved placeholders → ready to submit.

## Why this matters

A manuscript that conflates pilot data with final data is weakly
auditable: a reviewer can't tell which numbers reflect the structural
guarantees the paper claims, and the authors can't either after the
work has been refactored. The macros above turn that ambiguity into a
file-system property — `grep` answers the question.

## Related

- [13_claims.md](13_claims.md) — verifiable `\vclaim{}` linked to scitex-clew session hashes
- [24_writing-proofreading-style.md](24_writing-proofreading-style.md) — `\placeholder{}` rendering + style rules
- [25_writing-attitude.md](25_writing-attitude.md) — tone, hedging, transparency
- [21_writing-proofreading.md](21_writing-proofreading.md) — full proofreading pass
- `~/.claude/skills/scitex/scientific/04_clew_*.md` — Clew-DAG-as-map vs Clew-DAG-as-evidence framing (the substrate the `\vclaim{}` chain rides on)

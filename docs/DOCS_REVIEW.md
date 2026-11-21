# Review packaged documentation updates

Run these contributor commands from the checkout root. Return to the
[README build overview](../README.md#mounted-editor-and-frontend-builds).

Refresh the packaged offline documentation separately with Python 3.11+ and
this checkout installed with its docs dependencies:

```bash
python -m pip install -e '.[docs,dev]'
python scripts/build_docs.py --receipt /tmp/writer-offline-docs.json
```

The `vendor-sphinx-html` workflow uses Python 3.11 and prepares a review artifact
on relevant pull requests and `develop` pushes. It has read-only repository
access: it cannot commit or push generated files to protected branches.

To prepare the same proposal, start from clean, committed source and a new or
empty output directory outside the checkout. The command runs the strict build
itself; it is separate from the local preview command above:

```bash
python scripts/prepare_docs_update.py --output /tmp/writer-docs-review
```

The artifact contains `bundle.patch`, `summary.txt`, a build receipt and a
manifest binding the patch to its source commit, Python and docs-tool versions.
It includes new binary assets and deletions without staging the caller's index.
Before writing the patch, summary or manifest, the helper checks that the
isolated Git index contains exactly the receipt's files and content bytes.
Ignored generated files or Git attributes/filters that change those bytes cause
refusal. Existing Git policies and the caller's staging are preserved. The
[owning Git tests](../tests/integration/test_writer_docs_review_staging.py) cover
line-ending normalization, ignored additions and binary CRLF preservation.
[Local clean-filter tests](../tests/integration/test_writer_docs_review_filters.py)
also check byte-changing refusal and byte-preserving patch replay, including
filenames with spaces and Unicode.
The patch sets standard `a/` and `b/` path prefixes so plain `git apply` works
even with local `diff.noprefix=true`; the repository setting is preserved.
[The prefix replay test](../tests/integration/test_writer_docs_review_prefixes.py)
checks modified, new binary and deleted documentation files.
Patch output also disables ANSI coloring, so local `color.ui=always` or
`color.diff=always` keeps producing a plain-apply artifact without changing
those settings. [Color replay tests](../tests/integration/test_writer_docs_review_indicators.py)
check both settings against the receipt and unchanged caller state.
Patch generation fixes unified context at three lines and uses Git’s built-in
diff renderer; the summary also bypasses external diff helpers. Local
`diff.context` and `diff.external` settings remain unchanged.
[Configured diff replay tests](../tests/integration/test_writer_docs_review_config.py)
check zero-context settings, plain apply, and an uninvoked owned external helper.
Check the source commit and patch hash in the manifest, review the changed paths
and contents, and use an isolated branch at that source commit:

```bash
git apply --check /tmp/writer-docs-review/bundle.patch
git apply /tmp/writer-docs-review/bundle.patch
git diff -- src/scitex_writer/_sphinx_html
```

Submit the reviewed result through a normal pull request. CI uploads the
candidate before failing when regenerated docs differ from committed source;
an uploaded artifact or successful build alone is not reviewed delivery or
whole-guide content acceptance. Use the recorded Python/tool versions when
comparing a regeneration, and keep earlier failed artifacts for diagnosis.


The docs build refuses a mismatched installed Writer version, keeps strict
Sphinx warnings enabled and checks the generated version before replacing the
packaged HTML. Its receipt binds the generated files; this is separate from
reviewing guide contents or deployment.

Source and existing controls: [strict builder](../scripts/build_docs.py),
[review helper](../scripts/prepare_docs_update.py),
[read-only workflow](../.github/workflows/vendor-sphinx-html.yml), and
[artifact replay tests](../tests/integration/test_writer_docs_review_artifact.py).

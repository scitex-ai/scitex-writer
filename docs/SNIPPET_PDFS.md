# Searchable section preview PDFs

Writer-generated section/snippet wrappers use T1-encoded Latin Modern outline
fonts and pdfTeX's `glyphtounicode` mapping. This preserves ligatures such as
`fi`, `ff`, `ffi` and `fl` during text extraction, search and copying. It is not
PDF/UA certification or a claim that documents have complete accessibility tags.
Complete LaTeX documents keep their author-supplied fonts and mapping policy;
Writer's complete-document path only injects requested dark-mode colors.

The native Debian/Ubuntu dependency list and Writer-owned container recipes
explicitly require the `lmodern` package. TeX Live installations need its
`lmodern.sty` and outline fonts plus `glyphtounicode.tex` from pdfTeX. The owned
TeX Live image's package check verifies the style, mapping file and `lmr10.pfb`.
Missing files cause compilation to fail; no intentional bitmap-font fallback is
provided. Existing images must be checked or rebuilt through their normal image
workflow; a Python package update does not install system fonts.

The section API's preview key includes path, buffer, color, Writer version and
an explicit rendering-format revision. This revision changes for this fix, so an
old bitmap-font PDF cannot satisfy a new-format preview request even during an
unreleased source preview. Old files are retained; no project cache deletion or
manuscript overwrite is needed. The normal package release version remains
owned by the release workflow.

A real owned no-shell-escape pdfLaTeX comparison reproduced broken ligature
extraction with the former T1 bitmap wrapper, then preserved
`Finding verified efficient affine workflow office.` with the outline wrapper
using both Poppler and PyMuPDF. The original demo PDF's glyphs rendered correctly;
the defect affected its text representation. This does not claim a full
manuscript-font migration or a new live deployment.

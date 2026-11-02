#!/usr/bin/env bash
# Real elsarticle regression: packaged title survives the frontmatter group.
set -euo pipefail
command -v pdflatex >/dev/null
command -v grep >/dev/null
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
title_tmp="$(mktemp -d /tmp/writer-title-scope.XXXXXX)"
trap 'rm -rf -- "$title_tmp"' EXIT
# Arrange: exact consumer template and engine hook, not generated substitutes.
cp "$repo_root/00_shared/title.tex" "$title_tmp/title.tex"
cp "$repo_root/00_shared/latex_styles/title_scope.tex" "$title_tmp/title_scope.tex"
cat > "$title_tmp/paper.tex" <<'TEX'
\documentclass{elsarticle}
\input{title_scope}
\begin{document}
\begin{frontmatter}
\input{title}
\author{Template regression}
\begin{abstract}Fresh template compile regression.\end{abstract}
\end{frontmatter}
\clearpage
\useelstitle
\end{document}
TEX
# Act: a real class/engine expands the delayed title after its defining group.
if ! (cd "$title_tmp" && pdflatex -halt-on-error -interaction=nonstopmode paper.tex > compile.stdout); then
    cat "$title_tmp/compile.stdout"
    exit 1
fi
# Assert: the template produces a PDF with no undefined control sequence.
test -s "$title_tmp/paper.pdf"
if grep -q 'Undefined control sequence' "$title_tmp/paper.log"; then
    cat "$title_tmp/compile.stdout"
    exit 1
fi
printf '%s\n' 'PASS: shared title survives frontmatter and PDF is produced'

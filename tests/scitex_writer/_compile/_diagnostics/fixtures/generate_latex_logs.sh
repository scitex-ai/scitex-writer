#!/bin/bash
# Regenerates the real pdflatex/bibtex logs used by the diagnostics tests.
# Usage: generate_latex_logs.sh [output-dir]  (needs TeX Live on PATH)
set -u
OUT=${1:-"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/latex_logs"}
WORK=$(mktemp -d)
mkdir -p "$OUT"
cd "$WORK"

run_case() {
    local name=$1 flags=$2
    mkdir -p "$WORK/$name"
    cd "$WORK/$name"
    cat > main.tex
    pdflatex $flags -interaction=nonstopmode main.tex > stdout.txt 2>&1
    echo "exit=$?" >> stdout.txt
    cp -f main.log "$OUT/$name.log"
    cd "$WORK"
}

mkdir -p "$WORK/undefined_control_sequence/contents"
cat > "$WORK/undefined_control_sequence/contents/intro.tex" <<'EOF'
\section{Introduction}
This paragraph is fine.
Here is a typo \foo in the text.
EOF
run_case undefined_control_sequence -file-line-error <<'EOF'
\documentclass{article}
\begin{document}
\input{contents/intro}
\end{document}
EOF

run_case undefined_control_sequence_classic "" <<'EOF'
\documentclass{article}
\begin{document}
Hello \foo world.
\end{document}
EOF

run_case missing_package -file-line-error <<'EOF'
\documentclass{article}
\usepackage{nonexistentpackagexyz}
\begin{document}
Hello.
\end{document}
EOF

run_case unicode_char_not_set_up -file-line-error <<'EOF'
\documentclass{article}
\usepackage[utf8]{inputenc}
\begin{document}
A stray bracket 」 here.
\end{document}
EOF

run_case missing_file -file-line-error <<'EOF'
\documentclass{article}
\usepackage{graphicx}
\begin{document}
\includegraphics{figures/does_not_exist}
\end{document}
EOF

run_case citation_undefined -file-line-error <<'EOF'
\documentclass{article}
\begin{document}
As shown by \cite{nobody2020}, see Section~\ref{sec:missing}.
\end{document}
EOF

run_case runaway_argument -file-line-error <<'EOF'
\documentclass{article}
\begin{document}
\textbf{This bold never closes

Second paragraph.
\end{document}
EOF

run_case emergency_stop -file-line-error <<'EOF'
\documentclass{article}
\begin{document}
Missing the end of the document.
EOF

run_case overfull_only_warning -file-line-error <<'EOF'
\documentclass{article}
\begin{document}
\noindent Averyveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryverylongunbreakablewordthatoverflows
\end{document}
EOF

run_case unknown_error -file-line-error <<'EOF'
\documentclass{article}
\begin{document}
\errmessage{Something custom went wrong}
\end{document}
EOF

mkdir -p "$WORK/bibtex_error" && cd "$WORK/bibtex_error"
cat > main.tex <<'EOF'
\documentclass{article}
\begin{document}
See \cite{knuth1984}.
\bibliographystyle{plain}
\bibliography{references_missing}
\end{document}
EOF
pdflatex -interaction=nonstopmode -file-line-error main.tex > /dev/null 2>&1
bibtex main > bibtex_stdout.txt 2>&1
cp -f main.blg "$OUT/bibtex_error.blg"

mkdir -p "$WORK/timeout" && cd "$WORK/timeout"
cat > main.tex <<'EOF'
\documentclass{article}
\def\loopforever{\message{still looping}\loopforever}
\begin{document}
\loopforever
\end{document}
EOF
timeout 2 pdflatex -interaction=nonstopmode -file-line-error main.tex > /dev/null 2>&1
head -c 3000 main.log > "$OUT/timeout.log"

mkdir -p "$WORK/engine_not_found" && cd "$WORK/engine_not_found"
env PATH=/nonexistent /bin/bash -c 'pdflatex -interaction=nonstopmode main.tex' > "$OUT/engine_not_found.txt" 2>&1

ls -la "$OUT"
rm -rf "$WORK"

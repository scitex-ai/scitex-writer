#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_compile/_diagnostics/test__analyse.py

"""analyse_latex_output against REAL pdflatex/bibtex logs.

The fixtures were produced by compiling tiny broken .tex files with TeX Live
(see fixtures/generate_latex_logs.sh); nothing here is hand-written log text.
"""

from pathlib import Path

from scitex_writer._compile._diagnostics import analyse_latex_output
from scitex_writer._compile._diagnostics._analyse import map_flattened_location
from scitex_writer._compile._diagnostics._model import LatexDiagnostic

LOGS = Path(__file__).parent / "fixtures" / "latex_logs"


def _log(name: str) -> str:
    return (LOGS / name).read_text(encoding="utf-8")


def _first(diagnostics):
    return diagnostics[0]


def test_undefined_control_sequence_is_classified():
    # Arrange
    log = _log("undefined_control_sequence.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert _first(diagnostics).cause == "undefined-control-sequence"


def test_undefined_control_sequence_points_at_the_included_file_and_line():
    # Arrange
    log = _log("undefined_control_sequence.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert _first(diagnostics).location == "contents/intro.tex:3"


def test_undefined_control_sequence_hint_names_the_command():
    # Arrange
    log = _log("undefined_control_sequence.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert _first(diagnostics).hint.startswith("\\foo is not defined")


def test_undefined_control_sequence_context_is_the_offending_input():
    # Arrange
    log = _log("undefined_control_sequence.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert _first(diagnostics).context == "Here is a typo \\foo in the text."


def test_classic_bang_error_is_located_through_the_file_stack():
    # Arrange
    log = _log("undefined_control_sequence_classic.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert _first(diagnostics).location == "main.tex:3"


def test_missing_package_is_classified():
    # Arrange
    log = _log("missing_package.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert [d.cause for d in diagnostics] == ["missing-package"]


def test_unicode_char_not_set_up_is_classified():
    # Arrange
    log = _log("unicode_char_not_set_up.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert _first(diagnostics).cause == "unicode-char-not-set-up"


def test_unicode_char_hint_names_the_code_point_and_the_character():
    # Arrange
    log = _log("unicode_char_not_set_up.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert _first(diagnostics).hint == (
        "U+300D 」 isn't supported by pdfLaTeX: remove it or compile with XeLaTeX"
    )


def test_missing_file_is_classified():
    # Arrange
    log = _log("missing_file.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert _first(diagnostics).cause == "missing-file"


def test_bibtex_error_is_classified():
    # Arrange
    blg = _log("bibtex_error.blg")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, bibliography_log_text=blg)
    # Assert
    assert _first(diagnostics).cause == "bibtex-error"


def test_undefined_citation_is_a_warning():
    # Arrange
    log = _log("citation_undefined.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=False, log_text=log)
    # Assert
    assert (_first(diagnostics).cause, _first(diagnostics).severity) == (
        "citation-undefined",
        "warning",
    )


def test_undefined_reference_is_a_warning():
    # Arrange
    log = _log("citation_undefined.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=False, log_text=log)
    # Assert
    assert diagnostics[1].cause == "reference-undefined"


def test_runaway_argument_is_classified_instead_of_its_emergency_stop():
    # Arrange
    log = _log("runaway_argument.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert [d.cause for d in diagnostics] == ["runaway-argument"]


def test_lone_emergency_stop_is_classified():
    # Arrange
    log = _log("emergency_stop.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert [d.cause for d in diagnostics] == ["emergency-stop"]


def test_overfull_box_is_reported_when_it_is_the_only_issue():
    # Arrange
    log = _log("overfull_only_warning.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=False, log_text=log)
    # Assert
    assert [d.cause for d in diagnostics] == ["overfull-only-warning"]


def test_timeout_is_classified():
    # Arrange
    log = _log("timeout.log")
    # Act
    diagnostics = analyse_latex_output(
        compile_failed=True, log_text=log, timed_out_after_seconds=300
    )
    # Assert
    assert _first(diagnostics).cause == "timeout"


def test_engine_not_found_is_classified():
    # Arrange
    console = _log("engine_not_found.txt")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, console_text=console)
    # Assert
    assert _first(diagnostics).cause == "engine-not-found"


def test_unrecognised_error_is_unknown_with_its_location():
    # Arrange
    log = _log("unknown_error.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert (_first(diagnostics).cause, _first(diagnostics).location) == (
        "unknown",
        "main.tex:3",
    )


def test_failure_without_any_error_yields_unknown_with_the_log_tail_as_context():
    # Arrange
    log = _log("overfull_only_warning.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    # Assert
    assert "Output written on main.pdf" in diagnostics[-1].context


def test_failure_without_any_error_hints_to_open_the_full_log():
    # Arrange
    console = "compile.sh: something went wrong before LaTeX ran"
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, console_text=console)
    # Assert
    assert "Show full log" in _first(diagnostics).hint


def test_failure_with_no_output_at_all_still_yields_a_diagnostic():
    # Arrange
    empty = ""
    # Act
    diagnostics = analyse_latex_output(compile_failed=True, log_text=empty)
    # Assert
    assert _first(diagnostics).cause == "unknown"


def test_successful_clean_compile_yields_no_diagnostics():
    # Arrange
    log = _log("overfull_only_warning.log").replace("Overfull", "Fine")
    # Act
    diagnostics = analyse_latex_output(compile_failed=False, log_text=log)
    # Assert
    assert diagnostics == []


def test_writer_manuscript_log_reports_every_error():
    # Arrange
    log = _log("writer_manuscript_undefined_and_unicode.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=False, log_text=log)
    # Assert
    assert [d.cause for d in diagnostics if d.is_error] == [
        "unicode-char-not-set-up",
        "undefined-control-sequence",
        "unicode-char-not-set-up",
        "undefined-control-sequence",
    ]


def test_writer_manuscript_excerpt_is_not_merged_with_the_help_text():
    # Arrange
    log = _log("writer_manuscript_undefined_and_unicode.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=False, log_text=log)
    # Assert
    assert diagnostics[1].context.endswith("A typo \\foo here and a stray bracket ...")


def test_error_inside_a_macro_names_the_undefined_command_from_its_expansion():
    # Arrange
    log = _log("writer_manuscript_undefined_and_unicode.log")
    # Act
    diagnostics = analyse_latex_output(compile_failed=False, log_text=log)
    # Assert
    assert diagnostics[3].hint.startswith("\\scitexmanuscripttitle is not defined")


def test_flattened_manuscript_line_maps_back_to_its_source_file(tmp_path):
    # Arrange
    (tmp_path / "01_manuscript" / "contents").mkdir(parents=True)
    (tmp_path / "01_manuscript" / "contents" / "intro.tex").write_text(
        "Intro\nBad \\foo\n"
    )
    (tmp_path / "01_manuscript" / "manuscript.tex").write_text(
        "\\begin{document}\n"
        "% File: ./01_manuscript/contents/intro.tex\n"
        "% ======\n"
        "Intro\nBad \\foo\n"
    )
    flattened = LatexDiagnostic(
        cause="undefined-control-sequence",
        severity="error",
        message="Undefined control sequence.",
        hint="fix it",
        file="01_manuscript/manuscript.tex",
        line=5,
    )
    # Act
    mapped = map_flattened_location(flattened, tmp_path)
    # Assert
    assert mapped.location == "01_manuscript/contents/intro.tex:2"


# EOF

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: scripts/python/check_citation_trust.py
#
# NO mocks / NO monkeypatch (PA-306). The check exposes a real dependency-
# injection seam -- ``run_check(..., verifier=...)`` -- whose default is
# ``default_verifier`` (scitex-scholar). Tests pass real callables through that
# seam plus real tmp_path projects with real .tex/.bib files, so every path
# (verified / hallucinated / scholar-absent / cache) is exercised without a
# network and without patching internals.
#
# The end-to-end CLI runs use --offline, which is deterministic: scholar's
# offline resolver never resolves, so nothing can be reported trustworthy.

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from _citation_trust_cache import cache_path  # noqa: E402
from check_citation_trust import (  # noqa: E402
    STATUS_SEVERITY,
    VerificationUnavailable,
    effective_severity,
    run_check,
)

_SCRIPT = ROOT_DIR / "scripts" / "python" / "check_citation_trust.py"

_TEX = r"""
\documentclass{article}
\begin{document}
Real \cite{Real2020}, bogus \cite{Bogus2099}, and bare \cite{NoIdent2021}.
\bibliography{bibliography}
\end{document}
"""

_BIB = """
@article{Real2020,
  title = {Attention is all you need},
  author = {Vaswani, Ashish},
  journal = {NeurIPS},
  year = {2017},
  doi = {10.48550/arXiv.1706.03762}
}
@article{Bogus2099,
  title = {Quantum telepathic gradient descent in fungal networks},
  author = {Nobody, A.},
  journal = {Journal of Things That Do Not Exist},
  year = {2099}
}
@book{NoIdent2021,
  title = {A book with no identifier at all},
  author = {Anon, B.},
  year = {2021}
}
"""


class _StubVerifier:
    """Real callable injected through the verifier seam (not a mock).

    Records how many times it was called and returns canned verdicts, so the
    caching behaviour is observable without a network.
    """

    def __init__(self, verdicts=None, raises=None):
        self.calls = 0
        self.verdicts = verdicts or []
        self.raises = raises

    def __call__(
        self, project_dir, bib=None, offline=False, min_confidence=0.8, cited_keys=None
    ):
        self.calls += 1
        self.cited_keys = cited_keys
        if self.raises is not None:
            raise self.raises
        return [dict(v) for v in self.verdicts]


def _project(tmp_path, bib_text=_BIB):
    contents = tmp_path / "01_manuscript" / "contents"
    contents.mkdir(parents=True)
    (contents / "main.tex").write_text(_TEX, encoding="utf-8")
    (contents / "bibliography.bib").write_text(bib_text, encoding="utf-8")
    return tmp_path


def _verdicts(real="verified", bogus="hallucinated", noident="unverified"):
    return [
        {"key": "Real2020", "status": real, "detail": "crossref", "confidence": 0.98},
        {"key": "Bogus2099", "status": bogus, "detail": "no index hit"},
        {"key": "NoIdent2021", "status": noident, "detail": "no identifier"},
    ]


# ----------------------------------------------------------- severity mapping


def test_status_severity_mapping_matches_agreed_contract():
    # Arrange
    # Act
    mapping = STATUS_SEVERITY
    # Assert
    assert mapping == {
        "verified": "info",
        "unverified": "warning",
        "stub": "warning",
        "unlinked": "warning",
        "hallucinated": "error",
        "lookup_failed": "warning",
    }


def test_hallucinated_is_error_at_error_level():
    # Arrange
    # Act
    severity = effective_severity("hallucinated", "error")
    # Assert
    assert severity == "error"


def test_hallucinated_clamps_to_warning_at_warn_level():
    # Arrange
    # Act
    severity = effective_severity("hallucinated", "warn")
    # Assert
    assert severity == "warning"


def test_unverified_stays_warning_at_error_level():
    # Arrange
    # Act
    severity = effective_severity("unverified", "error")
    # Assert
    assert severity == "warning"


def test_unknown_status_is_treated_as_error_never_pass():
    # Arrange
    # Act
    severity = effective_severity("some-future-status", "error")
    # Assert
    assert severity == "error"


# ------------------------------------------------------------- classification


def test_hallucinated_citation_fails_the_check_at_error_level(tmp_path):
    # Arrange
    project = _project(tmp_path)
    # Act
    code = run_check(
        project, level="error", offline=True, verifier=_StubVerifier(_verdicts())
    )
    # Assert
    assert code == 1


def test_hallucinated_citation_does_not_block_at_warn_level(tmp_path):
    # Arrange
    project = _project(tmp_path)
    # Act
    code = run_check(
        project, level="warn", offline=True, verifier=_StubVerifier(_verdicts())
    )
    # Assert
    assert code == 0


def test_all_verified_citations_pass_at_error_level(tmp_path):
    # Arrange
    project = _project(tmp_path)
    verifier = _StubVerifier(_verdicts(bogus="verified", noident="verified"))
    # Act
    code = run_check(project, level="error", verifier=verifier)
    # Assert
    assert code == 0


def test_hallucinated_key_is_named_in_the_report(tmp_path, capsys):
    # Arrange
    project = _project(tmp_path)
    run_check(project, level="error", offline=True, verifier=_StubVerifier(_verdicts()))
    # Act
    out = capsys.readouterr().out
    # Assert
    assert "Bogus2099" in out


def test_verified_citation_is_reported_as_a_pass(tmp_path, capsys):
    # Arrange
    project = _project(tmp_path)
    run_check(project, level="warn", offline=True, verifier=_StubVerifier(_verdicts()))
    # Act
    out = capsys.readouterr().out
    # Assert
    assert "[PASS]" in out


def test_level_off_disables_the_check(tmp_path, capsys):
    # Arrange
    project = _project(tmp_path)
    verifier = _StubVerifier(_verdicts())
    run_check(project, level="off", verifier=verifier)
    # Act
    calls = verifier.calls
    # Assert
    assert calls == 0


# ------------------------------------------------------------------ fail-loud


def test_absent_scholar_never_reports_citations_as_verified(tmp_path, capsys):
    # Arrange
    project = _project(tmp_path)
    unavailable = VerificationUnavailable("scitex_scholar.verify_cites is unavailable")
    run_check(project, level="warn", verifier=_StubVerifier(raises=unavailable))
    # Act
    out = capsys.readouterr().out
    # Assert
    assert "[PASS]" not in out


def test_absent_scholar_warns_loudly_at_warn_level(tmp_path, capsys):
    # Arrange
    project = _project(tmp_path)
    unavailable = VerificationUnavailable("scitex_scholar.verify_cites is unavailable")
    run_check(project, level="warn", verifier=_StubVerifier(raises=unavailable))
    # Act
    out = capsys.readouterr().out
    # Assert
    assert "could NOT be verified" in out


def test_absent_scholar_does_not_block_at_warn_level(tmp_path):
    # Arrange
    project = _project(tmp_path)
    unavailable = VerificationUnavailable("scitex_scholar.verify_cites is unavailable")
    # Act
    code = run_check(project, level="warn", verifier=_StubVerifier(raises=unavailable))
    # Assert
    assert code == 0


def test_absent_scholar_fails_the_build_at_error_level(tmp_path):
    # Arrange
    project = _project(tmp_path)
    unavailable = VerificationUnavailable("scitex_scholar.verify_cites is unavailable")
    # Act
    code = run_check(project, level="error", verifier=_StubVerifier(raises=unavailable))
    # Assert
    assert code == 1


def test_verifier_crash_is_reported_as_unrunnable_not_pass(tmp_path):
    # Arrange
    project = _project(tmp_path)
    boom = VerificationUnavailable("verify_cites() failed: ConnectionError: no network")
    # Act
    code = run_check(project, level="error", verifier=_StubVerifier(raises=boom))
    # Assert
    assert code == 1


def test_cite_key_without_a_verdict_is_reported_as_unverified(tmp_path, capsys):
    # Arrange
    project = _project(tmp_path)
    partial = _StubVerifier([_verdicts()[0]])  # only Real2020 comes back
    run_check(project, level="warn", offline=True, verifier=partial)
    # Act
    out = capsys.readouterr().out
    # Assert
    assert "NO verdict from scitex-scholar" in out


# ------------------------------------------------- lookup failed (rate limit)


def _rate_limited(key="Real2020"):
    return {
        "key": key,
        "status": "lookup_failed",
        "detail": "lookup rate-limited: crossref: rate-limited (HTTP 429)",
    }


def test_rate_limited_lookup_is_not_reported_as_unverified(tmp_path, capsys):
    """Regression: a 429 from the metadata service surfaced as "weak title
    match" (UNVERIFIED). It must be reported as a lookup failure."""
    # Arrange
    project = _project(tmp_path)
    verdicts = [_rate_limited()] + _verdicts()[1:]
    # Act
    run_check(project, level="warn", verifier=_StubVerifier(verdicts))
    out = capsys.readouterr().out
    # Assert
    assert "LOOKUP_FAILED" in out and "UNRECOGNISED" not in out


def test_rate_limited_lookup_is_never_reported_as_trustworthy(tmp_path, capsys):
    # Arrange
    project = _project(tmp_path)
    # Act
    run_check(project, level="warn", verifier=_StubVerifier([_rate_limited()]))
    out = capsys.readouterr().out
    # Assert
    assert "trustworthy)" not in out


def test_rate_limited_lookup_does_not_block_at_error_level(tmp_path):
    """A transient service condition is a loud warning, not a content FAIL."""
    # Arrange
    project = _project(tmp_path)
    verdicts = [_rate_limited(k) for k in ("Real2020", "Bogus2099", "NoIdent2021")]
    # Act
    code = run_check(project, level="error", verifier=_StubVerifier(verdicts))
    # Assert
    assert code == 0


def test_rate_limited_verdict_is_not_cached(tmp_path):
    """A throttled lookup must be retried next compile, not frozen for the
    cache TTL."""
    # Arrange
    project = _project(tmp_path)
    verdicts = [_rate_limited()] + _verdicts()[1:]
    verifier = _StubVerifier(verdicts)
    run_check(project, level="warn", verifier=verifier)
    # Act
    run_check(project, level="warn", verifier=verifier)
    # Assert
    assert verifier.cited_keys == ["Real2020"]


def test_verifier_is_given_the_gate_cited_keys(tmp_path):
    """The gate's own cited set (not a re-scan of every .tex) is verified."""
    # Arrange
    project = _project(tmp_path)
    verifier = _StubVerifier(_verdicts())
    # Act
    run_check(project, level="warn", verifier=verifier)
    # Assert
    assert verifier.cited_keys == ["Bogus2099", "NoIdent2021", "Real2020"]


# --------------------------------------------------------------------- cache


def test_online_verdicts_are_written_to_the_cache(tmp_path):
    # Arrange
    project = _project(tmp_path)
    run_check(project, level="warn", verifier=_StubVerifier(_verdicts()))
    # Act
    exists = cache_path(project).is_file()
    # Assert
    assert exists is True


def test_offline_verdicts_are_never_cached(tmp_path):
    # Arrange
    project = _project(tmp_path)
    run_check(project, level="warn", offline=True, verifier=_StubVerifier(_verdicts()))
    # Act
    exists = cache_path(project).exists()
    # Assert
    assert exists is False


def test_second_run_serves_verdicts_from_the_cache(tmp_path):
    # Arrange
    project = _project(tmp_path)
    verifier = _StubVerifier(_verdicts())
    run_check(project, level="warn", verifier=verifier)
    # Act
    run_check(project, level="warn", verifier=verifier)
    # Assert
    assert verifier.calls == 1


def test_editing_a_bib_entry_reverifies_that_citation(tmp_path):
    # Arrange
    project = _project(tmp_path)
    verifier = _StubVerifier(_verdicts())
    run_check(project, level="warn", verifier=verifier)
    edited = _BIB.replace("Attention is all you need", "Attention is not all you need")
    (project / "01_manuscript" / "contents" / "bibliography.bib").write_text(
        edited, encoding="utf-8"
    )
    # Act
    run_check(project, level="warn", verifier=verifier)
    # Assert
    assert verifier.calls == 2


def test_no_cache_flag_forces_reverification(tmp_path):
    # Arrange
    project = _project(tmp_path)
    verifier = _StubVerifier(_verdicts())
    run_check(project, level="warn", verifier=verifier)
    # Act
    run_check(project, level="warn", use_cache=False, verifier=verifier)
    # Assert
    assert verifier.calls == 2


def test_cached_hallucination_still_fails_at_error_level(tmp_path):
    # Arrange
    project = _project(tmp_path)
    verifier = _StubVerifier(_verdicts())
    run_check(project, level="warn", verifier=verifier)
    # Act
    code = run_check(project, level="error", verifier=verifier)
    # Assert
    assert code == 1


# ------------------------------------------------- LIVE upstream (opt-in, net)
#
# Everything above drives the check through the ``verifier`` injection seam (or
# scholar's deterministic offline mode). That pins our status -> severity
# MAPPING, but it can never observe whether the REAL upstream
# (``scitex_scholar.verify_cites``) is capable of returning VERIFIED at all --
# and that blindness is not hypothetical: every scitex-scholar before 1.5.0 had
# a metadata-nesting bug that made a VERIFIED verdict structurally impossible,
# and the whole offline suite stayed green through it.
#
# The two tests below close that hole. They run writer's real check
# (``run_check`` with its DEFAULT verifier == ``default_verifier`` ==
# scitex-scholar) over a real tmp project, WITH NETWORK. They are OPT-IN and
# skipped by default so the rest of the suite (and CI) stays network-free and
# deterministic:
#
#     SCITEX_WRITER_NETWORK_TESTS=1 pytest tests/scripts/python/test_check_citation_trust.py -k live
#
# ``pytest.mark.skipif`` is a gate, not a mock -- no internals are patched here.

NETWORK_TESTS_ENV = "SCITEX_WRITER_NETWORK_TESTS"

live_network = pytest.mark.skipif(
    os.environ.get(NETWORK_TESTS_ENV, "0") != "1",
    reason=(
        f"live-network test: opt in with {NETWORK_TESTS_ENV}=1 "
        f"(needs scitex-scholar>=1.5.0 + internet)"
    ),
)

# A real, famous CrossRef-indexed paper: LeCun, Bengio & Hinton, Nature (2015).
_LIVE_TEX = r"""
\documentclass{article}
\begin{document}
Deep learning \cite{LeCun2015}.
\bibliography{bibliography}
\end{document}
"""

_LIVE_BIB = """
@article{LeCun2015,
  title = {Deep learning},
  author = {LeCun, Yann and Bengio, Yoshua and Hinton, Geoffrey},
  journal = {Nature},
  year = {2015},
  doi = {10.1038/nature14539}
}
"""

# No identifier, invented title, invented venue -- indexed nowhere.
_FABRICATED_TEX = r"""
\documentclass{article}
\begin{document}
Fabricated \cite{Fabricated2099}.
\bibliography{bibliography}
\end{document}
"""

_FABRICATED_BIB = """
@article{Fabricated2099,
  title = {Quantum telepathic gradient descent in fungal mycelial networks},
  author = {Nobody, A.},
  journal = {Journal of Things That Do Not Exist},
  year = {2099}
}
"""


def _live_project(tmp_path, tex_text, bib_text):
    contents = tmp_path / "01_manuscript" / "contents"
    contents.mkdir(parents=True)
    (contents / "main.tex").write_text(tex_text, encoding="utf-8")
    (contents / "bibliography.bib").write_text(bib_text, encoding="utf-8")
    return tmp_path


@live_network
def test_live_real_crossref_doi_is_verified_by_upstream_scholar(tmp_path, capsys):
    """Proves the REAL upstream can produce a VERIFIED verdict end-to-end.

    The 41 offline/DI tests pin the status -> severity MAPPING; only this test
    proves scitex-scholar can actually classify a real citation as VERIFIED.
    Without it, a broken scholar release (as every version < 1.5.0 was) would be
    invisible to us -- the whole suite would stay green while the check could
    never pass a single citation.
    """
    # Arrange
    project = _live_project(tmp_path, _LIVE_TEX, _LIVE_BIB)
    run_check(project, level="error", use_cache=False)
    # Act
    out = capsys.readouterr().out
    # Assert
    assert "1 citation(s) resolve to a real source" in out


@live_network
def test_live_fabricated_entry_is_classified_hallucinated_by_upstream(tmp_path, capsys):
    """Proves the live check DISCRIMINATES, not just that it says yes to all.

    Companion to the VERIFIED case: a real upstream run over a fabricated entry
    must come back HALLUCINATED. A scholar that verified everything would pass
    the positive test alone.
    """
    # Arrange
    project = _live_project(tmp_path, _FABRICATED_TEX, _FABRICATED_BIB)
    run_check(project, level="error", use_cache=False)
    # Act
    out = capsys.readouterr().out
    # Assert
    assert "classified HALLUCINATED" in out


# A real arXiv paper cited the way arXiv's own "export citation" emits it:
# bare `eprint` + `archivePrefix`, no DOI. The dominant citation form in ML/CS.
_EPRINT_TEX = r"""
\documentclass{article}
\begin{document}
Transformers \cite{Vaswani2017}.
\bibliography{bibliography}
\end{document}
"""

_EPRINT_BIB = """
@article{Vaswani2017,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish},
  eprint = {1706.03762},
  archivePrefix = {arXiv},
  year = {2017}
}
"""

# The SAME real paper as _LIVE_BIB, with the DOI removed. Exists, title matches
# perfectly -- and must STILL not verify, because nothing identifies it.
_TITLE_ONLY_TEX = _LIVE_TEX

_TITLE_ONLY_BIB = """
@article{LeCun2015,
  title = {Deep learning},
  author = {LeCun, Yann and Bengio, Yoshua and Hinton, Geoffrey},
  journal = {Nature},
  year = {2015}
}
"""


@live_network
def test_live_bare_arxiv_eprint_is_verified_by_upstream(tmp_path, capsys):
    """arXiv's own citation format must verify -- it is the ML/CS default.

    Before scholar 1.5.2 the `eprint` VALUE was discarded and the entry fell
    through to a title search, so this exact citation classified UNVERIFIED for
    one caller and VERIFIED for another, minutes apart.
    """
    # Arrange
    project = _live_project(tmp_path, _EPRINT_TEX, _EPRINT_BIB)
    run_check(project, level="error", use_cache=False)
    # Act
    out = capsys.readouterr().out
    # Assert
    assert "1 citation(s) resolve to a real source" in out


@live_network
def test_live_title_only_entry_is_not_verified_despite_being_real(tmp_path, capsys):
    """The correctness pin: a REAL paper with NO identifier must NOT verify.

    This entry is the same Nature paper as the VERIFIED case, minus its DOI. It
    exists and its title matches exactly -- and it must still come back
    unverified, because a fuzzy title match against a live index is not evidence:
    it is non-deterministic, so the same entry could pass on one run and fail on
    the next. Honest uncertainty beats a lucky pass; a verifier that is right by
    chance gives you no way to know which citations you can actually trust.

    If this test ever goes green on a "verified" line, the title-search fallback
    has come back and every guarantee this check makes is void.
    """
    # Arrange
    project = _live_project(tmp_path, _TITLE_ONLY_TEX, _TITLE_ONLY_BIB)
    run_check(project, level="warn", use_cache=False)
    # Act
    out = capsys.readouterr().out
    # Assert
    assert "resolve to a real source" not in out


# ----------------------------------------------------------------- end-to-end


def _run_cli(project, *extra):
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(Path(project) / "_home"),
    }
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(project), *extra],
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_offline_run_exits_zero_at_default_warn_level(tmp_path):
    # Arrange
    project = _project(tmp_path)
    # Act
    proc = _run_cli(project, "--offline")
    # Assert
    assert proc.returncode == 0


def test_cli_offline_run_exits_one_at_error_level(tmp_path):
    # Arrange
    project = _project(tmp_path)
    # Act
    proc = _run_cli(project, "--offline", "--level", "error")
    # Assert
    assert proc.returncode == 1


def test_cli_offline_run_never_reports_a_pass(tmp_path):
    # Arrange
    project = _project(tmp_path)
    # Act
    proc = _run_cli(project, "--offline", "--level", "warn")
    # Assert
    assert "[PASS]" not in proc.stdout


def test_cli_level_off_exits_zero_and_says_disabled(tmp_path):
    # Arrange
    project = _project(tmp_path)
    # Act
    proc = _run_cli(project, "--level", "off")
    # Assert
    assert "disabled (level=off)" in proc.stdout


# EOF

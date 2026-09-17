#!/usr/bin/env bash
# Runs INSIDE the reused scitex-ci SIF (apptainer exec — invoked via
# exec-in-sif.sh). Builds scitex-writer's wheel + sdist into ./dist/.
#
# WHY build in the SIF: the self-hosted Spartan runner has no Python on the
# bare node (the whole reason the old `actions/setup-python@v5` step failed:
# "version 3.x not found for this OS"). The SIF bakes python 3.11/3.12/3.13 +
# pip + uv at /opt/venv-<ver>, exactly like the working pytest-matrix CI.
#
# `python -m build` needs the `build` frontend, which is NOT baked in the SIF
# (only scitex-dev[all,dev] deps are). Mirror run-in-sif.sh: install `build`
# into a writable --target on node-local /tmp and put it on PYTHONPATH. The
# SIF's /opt/venv-* are root-owned + RO and the compute-node HOME is RO inside
# the container, so a normal install fails Permission denied — a --target on
# writable scratch sidesteps both.
#
# Fail-loud (operator directive): a missing interpreter or a failed build is a
# HARD error, never a silent fallback.
set -euo pipefail

V="${1:-3.12}"
VENV="/opt/venv-$V"
PY="$VENV/bin/python"
test -x "$PY" || {
    echo "::error::baked python missing in $VENV — rebuild the SIF: scitex-container apptainer build ci-cpu"
    exit 1
}

export LC_ALL=C.UTF-8 LANG=C.UTF-8

# Writable scratch (the runner's TMPDIR=~/.cache/tmp is a host path that does
# NOT resolve inside the container). Node-local /tmp is writable + ephemeral.
TMPDIR="/tmp/build-scitex_writer-${GITHUB_RUN_ID:-0}-${GITHUB_RUN_ATTEMPT:-0}-$V"
export TMPDIR
rm -rf "$TMPDIR"
mkdir -p "$TMPDIR/site" "$TMPDIR/uv-cache"

# The compute-node $HOME is RO inside the container — point every cache the
# installer might touch at the writable scratch (else uv/pip die creating
# ~/.cache).
export UV_CACHE_DIR="$TMPDIR/uv-cache"
export XDG_CACHE_HOME="$TMPDIR"
export PIP_CACHE_DIR="$TMPDIR/pip-cache"

# A VIRTUAL_ENV leaked from the runner profile (~/.env-3.11) is a broken
# symlink in here; unset it so no tool follows it.
unset VIRTUAL_ENV || true

export PATH="$VENV/bin:$PATH"
echo "build: py=$("$PY" -V) target=$TMPDIR/site"

# Install the PEP 517 build frontend into the writable target (uv fast path,
# pip safety net), then build with it. Clean dist/ first so only the freshly
# built artifacts are uploaded.
uv pip install --python "$PY" --target="$TMPDIR/site" build ||
    "$PY" -m pip install --target="$TMPDIR/site" build

export PYTHONPATH="$TMPDIR/site${PYTHONPATH:+:$PYTHONPATH}"

rm -rf dist
"$PY" -m build --outdir dist

echo "=== built artifacts ==="
ls -l dist
# fail-loud: refuse to continue the pipeline with an empty dist/.
test -n "$(ls -A dist 2>/dev/null)" || {
    echo "::error::python -m build produced no artifacts in dist/"
    exit 1
}

# Post-build import gate: install the freshly built wheel into a CLEAN venv and
# import the public entrypoint. `python -m build` builds the wheel FROM the
# sdist, so an sdist `exclude` that drops a packaged submodule (the 2.18.0–
# 2.26.0 _dataclasses/config outage: `import scitex_writer.writer` →
# ModuleNotFoundError on clean installs) fails HERE, before the artifact is
# uploaded and long before publish. A clean venv (not the build --target) is
# used so nothing on PYTHONPATH masks a missing packaged file.
WHEEL="$(ls dist/*.whl 2>/dev/null | head -1)"
test -n "$WHEEL" || {
    echo "::error::no wheel in dist/ to verify"
    exit 1
}
CLEANVENV="$TMPDIR/wheelcheck-venv"
rm -rf "$CLEANVENV"
"$PY" -m venv "$CLEANVENV"
"$CLEANVENV/bin/python" -m pip install --upgrade pip >/dev/null
"$CLEANVENV/bin/python" -m pip install "$WHEEL"
"$CLEANVENV/bin/python" -c "import scitex_writer.writer; print('wheel import OK:', '$WHEEL')"
# Name the exact submodule the outage dropped so a regression is unambiguous.
"$CLEANVENV/bin/python" -c "from scitex_writer._dataclasses.config import WriterConfig; print('WriterConfig OK')"

# Post-build CONTENT gate for the vendored scripts — same lesson as the import
# gate above, one artefact further out. The refresh that heals an existing
# workspace reads the INSTALLED package's scripts/ (`package_scripts_dir`), and
# because `python -m build` builds the wheel FROM the sdist, a wheel can lose
# them without any import breaking: the published 2.43.3 wheel shipped 4 files
# under scitex_writer/scripts/ (the READMEs the sdist happened to match) while
# the source tree had 122, and nothing failed until someone tried to heal a
# workspace in the field. Assert the KEY FILE is in the artifact, by exact
# member name, so the failure names the gap instead of hinting at it.
KEY_SCRIPT="scitex_writer/scripts/shell/modules/check_dependancy_commands.sh"
"$CLEANVENV/bin/python" - "$WHEEL" "$KEY_SCRIPT" <<'PY'
import sys, zipfile

wheel, key = sys.argv[1], sys.argv[2]
names = zipfile.ZipFile(wheel).namelist()
scripts = [n for n in names if n.startswith("scitex_writer/scripts/")]
if key not in names:
    print(
        f"::error::wheel {wheel} does not ship the vendored scripts: "
        f"{key} is absent ({len(scripts)} file(s) under scitex_writer/scripts/). "
        "A wheel install cannot self-heal its workspace's scripts without them. "
        "Check that the SDIST includes /scripts — the wheel is built from it."
    )
    raise SystemExit(1)
print(f"vendored scripts OK: {len(scripts)} file(s), key file present")

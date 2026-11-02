# Writer CI and release contract

The normal contributor install is `python -m pip install -e '.[dev]'`.
It declares the build tool and Dev>=0.62.7 used by the release-boundary tests
and the public private-cluster helper. SDK>=0.3.17 and LivePaper>=0.2.20 are
required for the frontend build; verify these distributions before installing.

## Mandatory private PostgreSQL

Ordinary PR and nightly matrices use the existing shared `pre_test_command`
input to opt into the leaf `writer_ci_postgres` pytest plugin. Preparation only
exports the module path, pytest option, mandatory-store flag and an unreachable
initial test DSN; a disabled bootstrap cannot turn store tests into skips.
Database startup happens after the
normal dependency install. The plugin starts one controller-owned cluster
before root conftest reads its test DSN. Xdist workers inherit that same required
cluster. Pytest config cleanup closes it on completion or cancellation.

The SIF runner invokes `.github/ci/with-test-postgres.py` around the complete
pytest command. It uses `scitex_dev.store.testing.ephemeral_cluster_dsn()`:
each run gets unique PGDATA and a Unix socket under a private temporary root,
with TCP listening disabled. PostgreSQL server binaries are a declared dependency
of the canonical Dev `ci-cpu.def` and are present in the pinned CI image.
Missing tools or failed startup stop the job before tests.

The driver clears inherited libpq connection settings and supplies its own test
DSN, role and empty private credential file before pytest and xdist import.
`SCITEX_WRITER_TEST_PG_REQUIRED=1` makes unavailable store coverage an error.
The production-system-ID refusal in `tests/conftest.py` stays unchanged.

The public context removes the cluster on success, failure and cancellation.
The existing SIF runner owns the test process group, propagates signals and
checks that its children are gone before deleting its outer scratch directory.
Cancellation arriving during child admission is retained until PID, process
group and kernel birth registration finish, then follows the same guarded
cancellation path. Scheduling-barrier regressions cover INT and TERM before PID
registration, before birth capture and during birth capture for all three release
drivers; unrelated processes and the existing deadlines remain protected.
Timed signal fixtures keep scripts and witnesses on the /tmp filesystem,
preserving an already-local inherited private parent. Their stdlib-only recorder
runs with isolated Python startup, so runner-workspace disk stalls and unrelated
site hooks do not become false descendant-liveness failures.
Real integration tests exercise SQL writes, success/failure/signal status,
closed TCP listening and cleanup. A local developer with server tools can use:

```bash
python .github/ci/with-test-postgres.py -- python -m pytest tests -q
```

## Release identity and dependency gates

`tests/integration/test_release_boundary.py` invokes the archive, metadata,
Git identity and owned-process lifecycle controls in ordinary PR/nightly test
space. The same controls run explicitly before publication. Metadata baselines
come from one cached real PEP517 wheel build of the exact tracked source.
Negative controls mutate individual boundaries; source-version and dependency
changes need no hand-edited metadata literals.

The tag-driven release workflow requires source already promoted to `main`,
checks the immutable tag/version/commit association, tests through the admitted
pinned SIF, and verifies whole wheel/sdist proof before the existing OIDC
publisher. Normal dependency resolution remains mandatory.

## Compile help and real compilation

Project-template global, document and recursive help read usage text before configuration,
initialization, log writes or dependency checks. Help works without yq, TeX,
project files or executable bits on delegated scripts. Actual compilation keeps
its fail-loud dependency checks, including a working Go yq.

External-network opt-ins, optional cross-package integrations and missing TeX
tools can still produce explicit skips in a local suite. A passing local run
must report those counts and the existing strict upstream citation-verification
xfail; it is not evidence that every optional integration was exercised.

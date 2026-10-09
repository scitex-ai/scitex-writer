"""Pure release-boundary controls using real archives and public Git fixtures."""

from __future__ import annotations

import base64
import contextlib
import copy
import csv
import ctypes
import functools
import hashlib
import importlib.util
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tomllib
import unittest
import zipfile
from pathlib import Path

if not __debug__:
    raise RuntimeError("Release identity controls require assertions enabled")

HERE = Path(__file__).parent
REPOSITORY = HERE.parent.parent
HELPER = HERE / "release-identity.py"
HELPER_SHA = hashlib.sha256(HELPER.read_bytes()).hexdigest()
SPEC = importlib.util.spec_from_file_location("owned_writer_release_identity", HELPER)
RELEASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELEASE)
CONFIG = "scitex_writer/_dataclasses/config/__init__.py"
SCRIPT = "scitex_writer/scripts/shell/modules/check_dependancy_commands.sh"
PREFIX = "repos/scitex-ai/scitex-writer"
OMITTED_GENERATED_LOGS = frozenset(
    {
        "scripts/shell/.compile_manuscript.sh.log",
        "scripts/shell/.compile_revision.sh.log",
        "scripts/shell/.compile_supplementary.sh.log",
    }
)


def git(*arguments):
    return subprocess.run(
        ["/usr/bin/git", "-C", str(REPOSITORY), *arguments],
        check=True,
        capture_output=True,
        timeout=7,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    ).stdout


SOURCE = git("rev-parse", "HEAD").decode().strip()
PYPROJECT = git("show", SOURCE + ":pyproject.toml")
VERSION = tomllib.loads(PYPROJECT.decode())["project"]["version"]
TAG = "v" + VERSION
DIST_INFO = "scitex_writer-" + VERSION + ".dist-info"
SDIST_ROOT = "scitex_writer-" + VERSION
CONFIG_BYTES = git("show", SOURCE + ":src/" + CONFIG)
SCRIPT_BYTES = git(
    "show", SOURCE + ":scripts/shell/modules/check_dependancy_commands.sh"
)


@functools.lru_cache(maxsize=1)
def public_source_files():
    """Read tracked public fixture bytes, without importing product modules."""
    raw = git(
        "archive",
        SOURCE,
        "src/scitex_writer",
        "scripts",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "pyproject.toml",
    )
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for item in archive:
            if (
                item.isdir()
                or item.name in OMITTED_GENERATED_LOGS
                or item.name.startswith("src/scitex_writer/_django/frontend/node_modules/")
            ):
                continue
            if not item.isfile():
                raise AssertionError("unsupported tracked public fixture: " + item.name)
            files[item.name] = archive.extractfile(item).read()
    return files


def public_wheel_files():
    return {
        name.removeprefix("src/")
        if name.startswith("src/")
        else "scitex_writer/" + name: body
        for name, body in public_source_files().items()
        if name.startswith(("src/scitex_writer/", "scripts/"))
    }


# Actual static Hatchling metadata/entry-point projection of this source.
# The pure fixtures carry genuine requirements/extras/Python/entry points;
# dependency metadata changes require refreshing this independently produced fixture.
# Refreshed for 2.43.10: added pytest-testmon>=2.2.0 (extras all, dev) to both
# Metadata fixtures; version stamp 2.43.10. Verified against a genuine local
# `python -m hatchling build` of this source (wheel 82831465 METADATA 2.5).
GENERATED_METADATA = b"Metadata-Version: 2.4\nName: scitex-writer\nVersion: 2.43.10\nSummary: LaTeX manuscript compilation system for scientific documents with MCP server\nProject-URL: Homepage, https://github.com/ywatanabe1989/scitex-writer\nProject-URL: Documentation, https://scitex-writer.readthedocs.io\nProject-URL: Repository, https://github.com/ywatanabe1989/scitex-writer.git\nProject-URL: Issues, https://github.com/ywatanabe1989/scitex-writer/issues\nAuthor-email: Yusuke Watanabe <ywatanabe@scitex.ai>\nLicense-Expression: AGPL-3.0-only\nLicense-File: LICENSE\nKeywords: academic,bibliography,bibtex,compilation,latex,manuscript,mcp,mcp-server,paper,scientific-writing,scitex\nClassifier: Development Status :: 4 - Beta\nClassifier: Environment :: Console\nClassifier: Intended Audience :: Science/Research\nClassifier: Operating System :: OS Independent\nClassifier: Programming Language :: Python :: 3\nClassifier: Programming Language :: Python :: 3.10\nClassifier: Programming Language :: Python :: 3.11\nClassifier: Programming Language :: Python :: 3.12\nClassifier: Programming Language :: Python :: 3.13\nClassifier: Topic :: Scientific/Engineering\nClassifier: Topic :: Text Processing :: Markup :: LaTeX\nRequires-Python: >=3.10\nRequires-Dist: bibtexparser<2.0,>=1.4\nRequires-Dist: click>=8.0\nRequires-Dist: django>=4.2\nRequires-Dist: fastmcp>=2.0.0\nRequires-Dist: pandas>=2.0\nRequires-Dist: pillow>=9.0\nRequires-Dist: scitex-config>=0.3.6\nRequires-Dist: scitex-dev>=0.48.0\nRequires-Dist: scitex-logging>=0.2.1\nRequires-Dist: scitex-sdk>=0.3.1\nProvides-Extra: all\nRequires-Dist: myst-parser>=2.0; extra == 'all'\nRequires-Dist: openpyxl; extra == 'all'\nRequires-Dist: pre-commit>=3.5.0; extra == 'all'\nRequires-Dist: pytest-cov>=4.0.0; extra == 'all'\nRequires-Dist: pytest-testmon>=2.2.0; extra == 'all'\nRequires-Dist: pytest-xdist>=3.0.0; extra == 'all'\nRequires-Dist: pytest>=7.0.0; extra == 'all'\nRequires-Dist: pywebview>=4.0.0; extra == 'all'\nRequires-Dist: scitex-scholar>=1.5.2; extra == 'all'\nRequires-Dist: sphinx-autodoc-typehints>=1.25; extra == 'all'\nRequires-Dist: sphinx-copybutton>=0.5; extra == 'all'\nRequires-Dist: sphinx-rtd-theme>=2.0; extra == 'all'\nRequires-Dist: sphinx>=7.0; extra == 'all'\nProvides-Extra: dev\nRequires-Dist: openpyxl; extra == 'dev'\nRequires-Dist: pre-commit>=3.5.0; extra == 'dev'\nRequires-Dist: pytest-cov>=4.0.0; extra == 'dev'\nRequires-Dist: pytest-testmon>=2.2.0; extra == 'dev'\nRequires-Dist: pytest-xdist>=3.0.0; extra == 'dev'\nRequires-Dist: pytest>=7.0.0; extra == 'dev'\nRequires-Dist: scitex-scholar>=1.5.2; extra == 'dev'\nProvides-Extra: docs\nRequires-Dist: myst-parser>=2.0; extra == 'docs'\nRequires-Dist: sphinx-autodoc-typehints>=1.25; extra == 'docs'\nRequires-Dist: sphinx-copybutton>=0.5; extra == 'docs'\nRequires-Dist: sphinx-rtd-theme>=2.0; extra == 'docs'\nRequires-Dist: sphinx>=7.0; extra == 'docs'\nDescription-Content-Type: text/markdown\n"
# Genuine header bytes from the Hatchling 1.32.4 sdist-to-wheel build.
# Original Metadata 2.4 fixture above remains unchanged.
# Refreshed for 2.43.10 alongside the fixtures above (local genuine build):
# Wheel SHA256: 82831465ede25a8d2e12032f2e54200164ca8e7e738d58d6fb06a669b9da1f2f.
# Full METADATA SHA256: 6bcbabd8f5aec34e878d7c6b24616998a846928825a2e6583a75f4fe3d785280.
# Exact header SHA256: 5b77e4a649bbfb07fdbc123967eeecd1e5a478cfaca6eefc23c35e6fdf037848.
GENERATED_METADATA_25 = b"Metadata-Version: 2.5\nName: scitex-writer\nVersion: 2.43.10\nSummary: LaTeX manuscript compilation system for scientific documents with MCP server\nProject-URL: Homepage, https://github.com/ywatanabe1989/scitex-writer\nProject-URL: Documentation, https://scitex-writer.readthedocs.io\nProject-URL: Repository, https://github.com/ywatanabe1989/scitex-writer.git\nProject-URL: Issues, https://github.com/ywatanabe1989/scitex-writer/issues\nAuthor-email: Yusuke Watanabe <ywatanabe@scitex.ai>\nLicense-Expression: AGPL-3.0-only\nLicense-File: LICENSE\nKeywords: academic,bibliography,bibtex,compilation,latex,manuscript,mcp,mcp-server,paper,scientific-writing,scitex\nClassifier: Development Status :: 4 - Beta\nClassifier: Environment :: Console\nClassifier: Intended Audience :: Science/Research\nClassifier: Operating System :: OS Independent\nClassifier: Programming Language :: Python :: 3\nClassifier: Programming Language :: Python :: 3.10\nClassifier: Programming Language :: Python :: 3.11\nClassifier: Programming Language :: Python :: 3.12\nClassifier: Programming Language :: Python :: 3.13\nClassifier: Topic :: Scientific/Engineering\nClassifier: Topic :: Text Processing :: Markup :: LaTeX\nRequires-Python: >=3.10\nRequires-Dist: bibtexparser<2.0,>=1.4\nRequires-Dist: click>=8.0\nRequires-Dist: django>=4.2\nRequires-Dist: fastmcp>=2.0.0\nRequires-Dist: pandas>=2.0\nRequires-Dist: pillow>=9.0\nRequires-Dist: scitex-config>=0.3.6\nRequires-Dist: scitex-dev>=0.48.0\nRequires-Dist: scitex-logging>=0.2.1\nRequires-Dist: scitex-sdk>=0.3.1\nProvides-Extra: all\nRequires-Dist: myst-parser>=2.0; extra == 'all'\nRequires-Dist: openpyxl; extra == 'all'\nRequires-Dist: pre-commit>=3.5.0; extra == 'all'\nRequires-Dist: pytest-cov>=4.0.0; extra == 'all'\nRequires-Dist: pytest-testmon>=2.2.0; extra == 'all'\nRequires-Dist: pytest-xdist>=3.0.0; extra == 'all'\nRequires-Dist: pytest>=7.0.0; extra == 'all'\nRequires-Dist: pywebview>=4.0.0; extra == 'all'\nRequires-Dist: scitex-scholar>=1.5.2; extra == 'all'\nRequires-Dist: sphinx-autodoc-typehints>=1.25; extra == 'all'\nRequires-Dist: sphinx-copybutton>=0.5; extra == 'all'\nRequires-Dist: sphinx-rtd-theme>=2.0; extra == 'all'\nRequires-Dist: sphinx>=7.0; extra == 'all'\nProvides-Extra: dev\nRequires-Dist: openpyxl; extra == 'dev'\nRequires-Dist: pre-commit>=3.5.0; extra == 'dev'\nRequires-Dist: pytest-cov>=4.0.0; extra == 'dev'\nRequires-Dist: pytest-testmon>=2.2.0; extra == 'dev'\nRequires-Dist: pytest-xdist>=3.0.0; extra == 'dev'\nRequires-Dist: pytest>=7.0.0; extra == 'dev'\nRequires-Dist: scitex-scholar>=1.5.2; extra == 'dev'\nProvides-Extra: docs\nRequires-Dist: myst-parser>=2.0; extra == 'docs'\nRequires-Dist: sphinx-autodoc-typehints>=1.25; extra == 'docs'\nRequires-Dist: sphinx-copybutton>=0.5; extra == 'docs'\nRequires-Dist: sphinx-rtd-theme>=2.0; extra == 'docs'\nRequires-Dist: sphinx>=7.0; extra == 'docs'\nDescription-Content-Type: text/markdown\n"
GENERATED_ENTRY_POINTS = b"[console_scripts]\nscitex-writer = scitex_writer._cli:main\n\n[scitex.apps]\nwriter = scitex_writer._django.apps:WriterEditorConfig\n\n[scitex_dev.docs]\nscitex-writer = scitex_writer\n\n[scitex_dev.skills]\nscitex-writer = scitex_writer\n\n[scitex_dev.system_deps]\nscitex-writer = scitex_writer._core._system_deps:provide\n"


def metadata(version=VERSION, name="scitex-writer", duplicate=False):
    body = b"".join(
        ("Name: " + name + "\n").encode()
        if line.startswith(b"Name: ")
        else ("Version: " + version + "\n").encode()
        if line.startswith(b"Version: ")
        else line
        for line in GENERATED_METADATA.splitlines(keepends=True)
    )
    if duplicate:
        body += ("Version: " + version + "\n").encode()
    return body


def record_bytes(files, record_name):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for name, body in sorted(files.items()):
        digest = (
            base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip("=")
        )
        writer.writerow((name, "sha256=" + digest, str(len(body))))
    writer.writerow((record_name, "", ""))
    return output.getvalue().encode()


def wheel(
    files=None,
    version=VERSION,
    metadata_owner=DIST_INFO,
    record_owner=None,
    changes=None,
    modes=None,
    record_transform=None,
    duplicate=None,
    metadata_body=None,
    entry_points_body=None,
):
    bodies = (
        {CONFIG: CONFIG_BYTES, SCRIPT: SCRIPT_BYTES} if files is None else dict(files)
    )
    bodies[metadata_owner + "/METADATA"] = (
        metadata(version) if metadata_body is None else metadata_body
    )
    bodies[metadata_owner + "/entry_points.txt"] = (
        GENERATED_ENTRY_POINTS if entry_points_body is None else entry_points_body
    )
    bodies.setdefault(
        metadata_owner + "/licenses/LICENSE", git("show", SOURCE + ":LICENSE")
    )
    bodies[metadata_owner + "/WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: owned-fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    record = (record_owner or metadata_owner) + "/RECORD"
    encoded = record_bytes(bodies, record)
    bodies[record] = record_transform(encoded) if record_transform else encoded
    bodies.update(changes or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, body in sorted(bodies.items()):
            entry = zipfile.ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = (modes or {}).get(name, stat.S_IFREG | 420) << 16
            archive.writestr(entry, body)
        if duplicate:
            archive.writestr(duplicate, bodies[duplicate])
    return output.getvalue()


def sdist(
    files=None,
    version=VERSION,
    project=PYPROJECT,
    root=SDIST_ROOT,
    additions=None,
    omit=(),
    metadata_body=None,
):
    bodies = (
        {
            "src/" + CONFIG: CONFIG_BYTES,
            "scripts/shell/modules/check_dependancy_commands.sh": SCRIPT_BYTES,
        }
        if files is None
        else dict(files)
    )
    bodies.update(
        {"pyproject.toml": project, "PKG-INFO": metadata_body or metadata(version)}
    )
    for name in omit:
        bodies.pop(name)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz", compresslevel=1) as archive:
        directory = tarfile.TarInfo(root)
        directory.type = tarfile.DIRTYPE
        directory.mode = 493
        archive.addfile(directory)
        for name, body in sorted(bodies.items()):
            entry = tarfile.TarInfo(root + "/" + name)
            entry.size = len(body)
            entry.mode = 420
            archive.addfile(entry, io.BytesIO(body))
        for entry, body in additions or []:
            archive.addfile(entry, io.BytesIO(body) if body is not None else None)
    return output.getvalue()


@functools.lru_cache(maxsize=1)
def whole_archives():
    return (wheel(files=public_wheel_files()), sdist(files=public_source_files()))


def replace_record_size(raw):
    rows = list(csv.reader(io.StringIO(raw.decode())))
    for row in rows:
        if row[0] == CONFIG:
            row[2] = "999999"
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue().encode()


def routes(project=PYPROJECT):
    digest = hashlib.sha1(
        b"blob " + str(len(project)).encode() + b"\x00" + project
    ).hexdigest()
    return {
        (PREFIX + "/git/ref/tags/" + TAG, 200): {
            "ref": "refs/tags/" + TAG,
            "object": {"type": "commit", "sha": SOURCE},
        },
        (PREFIX + "/compare/" + SOURCE + "...main", 200): {
            "base_commit": {"sha": SOURCE},
            "status": "ahead",
        },
        (PREFIX + "/contents/pyproject.toml?ref=" + SOURCE, 200): {
            "encoding": "base64",
            "content": base64.b64encode(project).decode(),
            "sha": digest,
        },
    }


@contextlib.contextmanager
def source_commit_with_project(project):
    """Make an owned real Git source commit; original public refs stay unchanged."""
    with tempfile.TemporaryDirectory(prefix="writer-release-selection-") as temporary:
        directory = Path(temporary)
        source = directory / "public-source.git"
        environment = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_INDEX_FILE": str(directory / "owned-index"),
            "GIT_AUTHOR_NAME": "Public fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Public fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        }

        def command(*arguments, body=None):
            return subprocess.run(
                ["/usr/bin/git", *arguments],
                input=body,
                check=True,
                capture_output=True,
                timeout=7,
                env=environment,
            ).stdout

        command("clone", "--bare", "--shared", "--quiet", str(REPOSITORY), str(source))
        blob = command("-C", str(source), "hash-object", "-w", "--stdin", body=project)
        command("-C", str(source), "read-tree", SOURCE)
        command(
            "-C", str(source), "update-index", "--cacheinfo", "100644",
            blob.decode().strip(), "pyproject.toml",
        )
        tree = command("-C", str(source), "write-tree").decode().strip()
        commit = command(
            "-C", str(source), "commit-tree", tree, "-p", SOURCE,
            body=b"Disposable declared-selection control\n",
        ).decode().strip()
        yield source, commit


class QueryFixture:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def __call__(self, path, status=200):
        self.calls.append((path, status))
        if (path, status) not in self.values:
            raise AssertionError("unapproved deterministic request: " + path)
        return copy.deepcopy(self.values[path, status])


class ResponseFixture:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit):
        return self.body[:limit]


def admitted_routes():
    return {
        **routes(),
        ("orgs/scitex-ai/public_members/fixture-member", 204): {"status": 204},
    }


@contextlib.contextmanager
def environment_inputs(values):
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


@contextlib.contextmanager
def argument_inputs(values):
    previous = sys.argv
    sys.argv = list(values)
    try:
        yield
    finally:
        sys.argv = previous


def refusal(operation, exception=ValueError, message=None):
    try:
        operation()
    except exception as error:
        return message is None or message in str(error)
    return False


class TagAndAdmissionTests(unittest.TestCase):
    def test_exact_existing_tag_resolves_promoted_public_version(self):
        # Arrange
        query = QueryFixture(routes())
        # Act
        result = RELEASE.resolve(TAG, query)
        # Assert
        assert result == {"tag": TAG, "commit": SOURCE, "version": VERSION}

    def test_tag_path_and_shell_escapes_make_zero_requests(self):
        # Arrange
        for tag in (
            "v2.43.8/../../main",
            "v2.43.8?ref=main",
            "v2.43.8\nmain",
            "v2.43.8;echo bad",
            "v02.43.8",
            "$(anything)",
            "v2.43.8%2fmain",
        ):
            with self.subTest(tag=tag):
                query = QueryFixture({})
                # Act
                refused = refusal(lambda: RELEASE.resolve(tag, query), ValueError)
                requests = query.calls
                # Assert
                assert refused and requests == []

    def test_real_annotated_tag_chain(self):
        # Arrange
        values = routes()
        values[PREFIX + "/git/ref/tags/" + TAG, 200]["object"] = {
            "type": "tag",
            "sha": "a" * 40,
        }
        values[PREFIX + "/git/tags/" + "a" * 40, 200] = {
            "object": {"type": "commit", "sha": SOURCE}
        }
        # Act
        result = RELEASE.resolve(TAG, QueryFixture(values))["commit"]
        # Assert
        assert result == SOURCE

    def test_annotation_cycle_refused(self):
        # Arrange
        values = routes()
        values[PREFIX + "/git/ref/tags/" + TAG, 200]["object"] = {
            "type": "tag",
            "sha": "a" * 40,
        }
        values[PREFIX + "/git/tags/" + "a" * 40, 200] = {
            "object": {"type": "tag", "sha": "b" * 40}
        }
        values[PREFIX + "/git/tags/" + "b" * 40, 200] = {
            "object": {"type": "tag", "sha": "a" * 40}
        }
        # Act
        refused = refusal(
            lambda: RELEASE.resolve(TAG, QueryFixture(values)), ValueError, "cyclic"
        )
        # Assert
        assert refused

    def test_annotation_depth_refused(self):
        # Arrange
        values = routes()
        values[PREFIX + "/git/ref/tags/" + TAG, 200]["object"] = {
            "type": "tag",
            "sha": "a" * 40,
        }
        for first, second in zip("abcde", "bcdef"):
            values[PREFIX + "/git/tags/" + first * 40, 200] = {
                "object": {"type": "tag", "sha": second * 40}
            }
        # Act
        refused = refusal(
            lambda: RELEASE.resolve(TAG, QueryFixture(values)), ValueError, "depth"
        )
        # Assert
        assert refused

    def test_wrong_ref_and_noncommit_object_refused(self):
        # Arrange
        for mutation in ("ref", "blob"):
            with self.subTest(mutation=mutation):
                values = routes()
                ref = values[PREFIX + "/git/ref/tags/" + TAG, 200]
                if mutation == "ref":
                    ref["ref"] = "refs/heads/main"
                else:
                    ref["object"]["type"] = "blob"
                # Act
                refused = refusal(
                    lambda: RELEASE.resolve(TAG, QueryFixture(values)), ValueError
                )
                # Assert
                assert refused

    def test_not_promoted_source_refused(self):
        # Arrange
        for status in ("behind", "diverged", "unknown"):
            with self.subTest(status=status):
                values = routes()
                values[PREFIX + "/compare/" + SOURCE + "...main", 200]["status"] = (
                    status
                )
                # Act
                refused = refusal(
                    lambda: RELEASE.resolve(TAG, QueryFixture(values)),
                    ValueError,
                    "promoted",
                )
                # Assert
                assert refused

    def test_comparison_base_identity_is_required(self):
        # Arrange
        values = routes()
        values[PREFIX + "/compare/" + SOURCE + "...main", 200]["base_commit"]["sha"] = (
            "f" * 40
        )
        # Act
        refused = refusal(
            lambda: RELEASE.resolve(TAG, QueryFixture(values)), ValueError, "promoted"
        )
        # Assert
        assert refused

    def test_source_version_tampering_has_valid_git_blob_but_is_refused(self):
        # Arrange
        changed = PYPROJECT.replace(
            ('version = "' + VERSION + '"').encode(), b'version = "99.99.99"'
        )
        # Act
        refused = refusal(
            lambda: RELEASE.resolve(TAG, QueryFixture(routes(changed))),
            ValueError,
            "metadata differ",
        )
        # Assert
        assert refused

    def test_source_metadata_git_blob_tampering_refused(self):
        # Arrange
        values = routes()
        values[PREFIX + "/contents/pyproject.toml?ref=" + SOURCE, 200]["sha"] = "0" * 40
        # Act
        refused = refusal(
            lambda: RELEASE.resolve(TAG, QueryFixture(values)),
            ValueError,
            "Git identity",
        )
        # Assert
        assert refused

    def test_both_actors_require_confirmed_membership(self):
        # Arrange
        environment = {
            "GITHUB_REPOSITORY": RELEASE.REPOSITORY,
            "GITHUB_ACTOR": "fixture-member",
            "GITHUB_TRIGGERING_ACTOR": "fixture-trigger",
        }
        values = {
            (f"orgs/scitex-ai/public_members/{actor}", 204): {"status": 204}
            for actor in ("fixture-member", "fixture-trigger")
        }
        query = QueryFixture(values)
        # Act
        with environment_inputs(environment):
            RELEASE.member_admission(query)
        result = set(query.calls)
        # Assert
        assert result == set(values)

    def test_unknown_membership_fails_closed(self):
        # Arrange
        environment = {
            "GITHUB_REPOSITORY": RELEASE.REPOSITORY,
            "GITHUB_ACTOR": "fixture-member",
            "GITHUB_TRIGGERING_ACTOR": "fixture-member",
        }
        query = QueryFixture(
            {("orgs/scitex-ai/public_members/fixture-member", 204): {"status": 404}}
        )
        with environment_inputs(environment):
            # Act
            refused = refusal(
                lambda: RELEASE.member_admission(query), ValueError, "not confirmed"
            )
            # Assert
            assert refused

    def test_foreign_repository_and_unknown_actor_make_zero_requests(self):
        # Arrange
        for changes in (
            {"GITHUB_REPOSITORY": "foreign/writer"},
            {"GITHUB_TRIGGERING_ACTOR": ""},
            {"GITHUB_ACTOR": "member/escape"},
        ):
            with self.subTest(changes=changes):
                environment = {
                    "GITHUB_REPOSITORY": RELEASE.REPOSITORY,
                    "GITHUB_ACTOR": "fixture-member",
                    "GITHUB_TRIGGERING_ACTOR": "fixture-member",
                    **changes,
                }
                query = QueryFixture({})
                with environment_inputs(environment):
                    # Act
                    refused = refusal(
                        lambda: RELEASE.member_admission(query), ValueError
                    )
                    # Assert
                requests = query.calls
                assert refused and requests == []


class HttpIdentityTests(unittest.TestCase):
    def test_actual_api_request_is_bounded_and_uses_existing_identity_protocol(self):
        # Arrange
        observed = []

        def fake(request, timeout):
            observed.append(
                (
                    request.full_url,
                    timeout,
                    request.get_header("Accept"),
                    request.get_header("X-github-api-version"),
                    request.get_header("Authorization"),
                )
            )
            return ResponseFixture(b'{"fixture":true}')

        # Act
        with environment_inputs({}):
            result = RELEASE.api("repos/scitex-ai/scitex-writer", open_url=fake)
        result = (result, observed)
        # Assert
        assert result == (
            {"fixture": True},
            [
                (
                    "https://api.github.com/repos/scitex-ai/scitex-writer",
                    10,
                    "application/vnd.github+json",
                    "2022-11-28",
                    None,
                )
            ],
        )

    def test_status_mismatch_and_oversized_body_fail_closed(self):
        # Arrange
        for response in (ResponseFixture(b"{}", 202), ResponseFixture(b"x" * 1048577)):
            with self.subTest(status=response.status, bytes=len(response.body)):
                # Act
                refused = refusal(
                    lambda: RELEASE.api(
                        "repos/scitex-ai/scitex-writer",
                        open_url=lambda request, timeout: response,
                    ),
                    ValueError,
                )
                # Assert
                assert refused

    def test_membership_204_requires_exact_response_status(self):
        # Arrange
        with environment_inputs({}):
            # Act
            result = RELEASE.api(
                "orgs/scitex-ai/public_members/fixture-member",
                status=204,
                open_url=lambda request, timeout: ResponseFixture(b"", 204),
            )
            # Assert
            assert result == {"status": 204}


class ResolveCliTests(unittest.TestCase):
    def test_real_resolve_cli_emits_bound_outputs_using_only_fake_network(self):
        # Arrange
        with tempfile.TemporaryDirectory(prefix="writer-resolve-output-") as directory:
            output = Path(directory) / "github-output"
            environment = {
                "GITHUB_REPOSITORY": RELEASE.REPOSITORY,
                "GITHUB_ACTOR": "fixture-member",
                "GITHUB_TRIGGERING_ACTOR": "fixture-member",
                "GITHUB_OUTPUT": str(output),
                "GITHUB_EVENT_NAME": "push",
                "GITHUB_SHA": SOURCE,
            }
            # Act
            with (
                environment_inputs(environment),
                argument_inputs([str(HELPER), "resolve", "--tag", TAG]),
                contextlib.redirect_stdout(io.StringIO()) as captured,
            ):
                RELEASE.main(query=QueryFixture(admitted_routes()))
            result = (json.loads(captured.getvalue()), output.read_text().splitlines())
            # Assert
            assert result == (
                {"tag": TAG, "commit": SOURCE, "version": VERSION},
                ["tag=" + TAG, "commit=" + SOURCE, "version=" + VERSION],
            )

    def test_push_commit_mismatch_refuses_before_emitting_output(self):
        # Arrange
        with tempfile.TemporaryDirectory(prefix="writer-resolve-output-") as directory:
            output = Path(directory) / "github-output"
            environment = {
                "GITHUB_REPOSITORY": RELEASE.REPOSITORY,
                "GITHUB_ACTOR": "fixture-member",
                "GITHUB_TRIGGERING_ACTOR": "fixture-member",
                "GITHUB_OUTPUT": str(output),
                "GITHUB_EVENT_NAME": "push",
                "GITHUB_SHA": "a" * 40,
            }
            with (
                environment_inputs(environment),
                argument_inputs([str(HELPER), "resolve", "--tag", TAG]),
            ):
                # Act
                refused = refusal(
                    lambda: RELEASE.main(query=QueryFixture(admitted_routes())),
                    ValueError,
                    "push event",
                )
                # Assert
                output_exists = output.exists()
            assert refused and not output_exists


class ArchiveTests(unittest.TestCase):
    def test_real_wheel_carries_actual_config_package_and_vendored_script(self):
        # Arrange
        # Act
        result = RELEASE.wheel_identity(wheel(), VERSION)["members"]
        # Assert
        assert result > 2

    def test_wheel_body_tampering_preserves_old_record_and_refuses(self):
        # Arrange
        # Act
        refused = refusal(
            lambda: RELEASE.wheel_identity(
                wheel(changes={CONFIG: CONFIG_BYTES + b"\n# changed\n"}), VERSION
            ),
            ValueError,
            "RECORD",
        )
        # Assert
        assert refused

    def test_record_hash_and_size_tampering_refused(self):
        # Arrange
        for changed in (
            lambda raw: raw.replace(b"sha256=", b"sha512=", 1),
            replace_record_size,
        ):
            with self.subTest(change=changed):
                # Act
                refused = refusal(
                    lambda: RELEASE.wheel_identity(
                        wheel(record_transform=changed), VERSION
                    ),
                    ValueError,
                    "RECORD",
                )
                # Assert
                assert refused

    def test_record_extra_or_missing_member_refused(self):
        # Arrange
        # Act
        extra_record_refused = refusal(
            lambda: RELEASE.wheel_identity(
                wheel(record_transform=lambda raw: b"unknown.py,,\n" + raw), VERSION
            ),
            ValueError,
            "RECORD",
        )
        unrecorded_refused = refusal(
            lambda: RELEASE.wheel_identity(
                wheel(changes={"unknown.py": b"new unrecorded member"}), VERSION
            ),
            ValueError,
            "unrecorded",
        )
        # Assert
        assert extra_record_refused and unrecorded_refused

    def test_wheel_version_tampering_refused(self):
        # Arrange
        # Act
        refused = refusal(
            lambda: RELEASE.wheel_identity(wheel(version="99.99.99"), VERSION),
            ValueError,
            "version",
        )
        # Assert
        assert refused

    def test_metadata_and_record_must_have_same_distribution_owner(self):
        # Arrange
        # Act
        refused = refusal(
            lambda: RELEASE.wheel_identity(
                wheel(record_owner="foreign-7.dist-info"), VERSION
            ),
            ValueError,
        )
        # Assert
        assert refused

    def test_wheel_member_escape_backslash_and_absolute_refused(self):
        # Arrange
        for name in ("../escape.py", "/absolute.py", "a\\escape.py"):
            with self.subTest(name=name):
                # Act
                refused = refusal(
                    lambda: RELEASE.wheel_identity(
                        wheel(changes={name: b"synthetic unsafe member"}), VERSION
                    ),
                    ValueError,
                )
                # Assert
                assert refused

    def test_wheel_symlink_and_special_mode_refused(self):
        # Arrange
        for mode in (stat.S_IFLNK | 511, stat.S_IFIFO | 384, stat.S_IFCHR | 384):
            with self.subTest(mode=mode):
                # Act
                refused = refusal(
                    lambda: RELEASE.wheel_identity(
                        wheel(modes={CONFIG: mode}), VERSION
                    ),
                    ValueError,
                )
                # Assert
                assert refused

    def test_wheel_duplicate_member_refused(self):
        # Arrange
        # Act
        refused = refusal(
            lambda: RELEASE.wheel_identity(wheel(duplicate=CONFIG), VERSION),
            ValueError,
            "duplicate",
        )
        # Assert
        assert refused

    def test_actual_source_sdist_is_accepted(self):
        # Arrange
        # Act
        result = RELEASE.sdist_identity(sdist(), VERSION)["members"]
        # Assert
        assert result > 3

    def test_metadata_only_sdist_is_refused(self):
        # Arrange
        # Act
        refused = refusal(
            lambda: RELEASE.sdist_identity(sdist(files={}), VERSION), ValueError
        )
        # Assert
        assert refused

    def test_tar_escape_and_absolute_member_refused(self):
        # Arrange
        for name in (SDIST_ROOT + "/../escape", "/absolute", "a\\escape"):
            with self.subTest(name=name):
                entry = tarfile.TarInfo(name)
                entry.size = 1
                # Act
                refused = refusal(
                    lambda: RELEASE.sdist_identity(
                        sdist(additions=[(entry, b"x")]), VERSION
                    ),
                    ValueError,
                )
                # Assert
                assert refused

    def test_tar_symbolic_and_hard_links_refused_without_dereference(self):
        # Arrange
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with self.subTest(kind=kind):
                entry = tarfile.TarInfo(SDIST_ROOT + "/public-link")
                entry.type = kind
                entry.linkname = "/synthetic-private-target"
                # Act
                refused = refusal(
                    lambda: RELEASE.sdist_identity(
                        sdist(additions=[(entry, None)]), VERSION
                    ),
                    ValueError,
                    "unsupported",
                )
                # Assert
                assert refused

    def test_tar_multiple_roots_refused(self):
        # Arrange
        entry = tarfile.TarInfo("other-root/public.py")
        entry.size = 1
        # Act
        refused = refusal(
            lambda: RELEASE.sdist_identity(sdist(additions=[(entry, b"x")]), VERSION),
            ValueError,
            "multiple roots",
        )
        # Assert
        assert refused

    def test_sdist_metadata_and_project_versions_must_agree(self):
        # Arrange
        for changed in (
            sdist(version="99.99.99"),
            sdist(
                project=PYPROJECT.replace(
                    ('version = "' + VERSION + '"').encode(), b'version = "99.99.99"'
                )
            ),
        ):
            with self.subTest(version_source=hashlib.sha256(changed).hexdigest()):
                # Act
                refused = refusal(
                    lambda: RELEASE.sdist_identity(changed, VERSION), ValueError
                )
                # Assert
                assert refused

    def test_sdist_duplicate_identity_headers_refused(self):
        # Arrange
        # Act
        refused = refusal(
            lambda: RELEASE.sdist_identity(
                sdist(metadata_body=metadata(duplicate=True)), VERSION
            ),
            ValueError,
        )
        # Assert
        assert refused


class WholeSourceTests(unittest.TestCase):
    def source_identity(self, wheel_raw=None, sdist_raw=None, commit=SOURCE):
        original_wheel, original_sdist = whole_archives()
        return RELEASE.source_payload_identity(
            wheel_raw or original_wheel,
            sdist_raw or original_sdist,
            commit,
            source_root=REPOSITORY,
        )

    def test_every_actual_tracked_package_and_script_matches_exact_git_source(self):
        # Arrange
        # Act
        identity = self.source_identity()
        result = (
            identity["git_commit"],
            identity["wheel_public_members"],
            identity["sdist_public_members"],
        )
        # Assert
        assert result == (SOURCE, len(public_wheel_files()), len(public_source_files()))

    def test_rehashed_wheel_payload_still_refuses_changed_public_bytes(self):
        # Arrange
        files = public_wheel_files()
        files[CONFIG] += b"\n# coordinated tamper\n"
        changed = wheel(files=files)
        RELEASE.wheel_identity(changed, VERSION)
        # Act
        refused = refusal(
            lambda: self.source_identity(wheel_raw=changed),
            ValueError,
            "public source bytes",
        )
        # Assert
        assert refused

    def test_missing_required_tracked_wheel_member_refused(self):
        # Arrange
        files = public_wheel_files()
        omitted = next((name for name in sorted(files) if name not in {CONFIG, SCRIPT}))
        del files[omitted]
        changed = wheel(files=files)
        RELEASE.wheel_identity(changed, VERSION)
        # Act
        refused = refusal(
            lambda: self.source_identity(wheel_raw=changed), ValueError, "membership"
        )
        # Assert
        assert refused

    def test_rehashed_foreign_wheel_package_member_refused(self):
        # Arrange
        files = public_wheel_files()
        files["scitex_writer/untracked_fixture.py"] = b"foreign package member\n"
        changed = wheel(files=files)
        RELEASE.wheel_identity(changed, VERSION)
        # Act
        refused = refusal(
            lambda: self.source_identity(wheel_raw=changed), ValueError, "membership"
        )
        # Assert
        assert refused

    def test_rehashed_payload_outside_package_and_dist_info_refused(self):
        # Arrange
        files = public_wheel_files()
        files["foreign_fixture.py"] = b"foreign top-level member\n"
        changed = wheel(files=files)
        RELEASE.wheel_identity(changed, VERSION)
        # Act
        refused = refusal(
            lambda: self.source_identity(wheel_raw=changed),
            ValueError,
            "undeclared payload",
        )
        # Assert
        assert refused

    def test_real_sdist_public_byte_tampering_refused(self):
        # Arrange
        files = dict(public_source_files())
        files["src/" + CONFIG] += b"\n# changed\n"
        changed = sdist(files=files)
        RELEASE.sdist_identity(changed, VERSION)
        # Act
        refused = refusal(
            lambda: self.source_identity(sdist_raw=changed),
            ValueError,
            "public source bytes",
        )
        # Assert
        assert refused

    def test_missing_tracked_sdist_payload_refused(self):
        # Arrange
        files = dict(public_source_files())
        del files["README.md"]
        changed = sdist(files=files)
        RELEASE.sdist_identity(changed, VERSION)
        # Act
        refused = refusal(
            lambda: self.source_identity(sdist_raw=changed), ValueError, "incomplete"
        )
        # Assert
        assert refused

    def test_untracked_extra_sdist_member_refused(self):
        # Arrange
        files = dict(public_source_files())
        files["untracked_fixture.txt"] = b"synthetic foreign member\n"
        changed = sdist(files=files)
        RELEASE.sdist_identity(changed, VERSION)
        # Act
        refused = refusal(
            lambda: self.source_identity(sdist_raw=changed),
            ValueError,
            "undeclared public payload",
        )
        # Assert
        assert refused

    def test_malformed_or_absent_source_commit_fails_closed(self):
        # Arrange
        for commit in ("not-a-commit", "0" * 40):
            with self.subTest(commit=commit):
                # Act
                refused = refusal(
                    lambda: self.source_identity(commit=commit), ValueError
                )
                # Assert
                assert refused


    def test_sdist_selection_refuses_missing_broad_or_fourth_exclusions(self):
        # Arrange
        literal = b'    "/scripts/shell/.compile_manuscript.sh.log",\n'
        candidates = (
            PYPROJECT.replace(literal, b"", 1),
            PYPROJECT.replace(literal, b'    "/scripts/**/*.log",\n', 1),
            PYPROJECT.replace(
                literal,
                literal
                + b'    "/scripts/shell/modules/check_dependancy_commands.sh",\n',
                1,
            ),
            PYPROJECT.replace(
                b"[tool.hatch.build.targets.sdist]\n",
                b"[tool.hatch.build.targets.sdist]\nignore-vcs = true\n",
                1,
            ),
        )
        for project in candidates:
            with self.subTest(project_sha256=hashlib.sha256(project).hexdigest()):
                if project == PYPROJECT:
                    raise RuntimeError("selection counterexample did not change source")
                files = dict(public_source_files())
                changed = sdist(files=files, project=project)
                RELEASE.sdist_identity(changed, VERSION)
                with source_commit_with_project(project) as (source, commit):
                    # Act
                    refused = refusal(
                        lambda: RELEASE.source_payload_identity(
                            whole_archives()[0], changed, commit, source_root=source
                        ),
                        ValueError,
                        "sdist selection",
                    )
                    # Assert
                    assert refused

    def test_each_declared_generated_log_is_refused_in_wheel(self):
        # Arrange
        for path in sorted(OMITTED_GENERATED_LOGS):
            with self.subTest(path=path):
                files = public_wheel_files()
                files["scitex_writer/" + path] = b"Disposable generated log\n"
                changed = wheel(files=files)
                RELEASE.wheel_identity(changed, VERSION)
                # Act
                refused = refusal(
                    lambda: self.source_identity(wheel_raw=changed),
                    ValueError,
                    "membership",
                )
                # Assert
                assert refused

    def test_each_declared_generated_log_is_refused_in_sdist(self):
        # Arrange
        for path in sorted(OMITTED_GENERATED_LOGS):
            with self.subTest(path=path):
                files = dict(public_source_files())
                files[path] = b"Disposable generated log\n"
                changed = sdist(files=files)
                RELEASE.sdist_identity(changed, VERSION)
                # Act
                refused = refusal(
                    lambda: self.source_identity(sdist_raw=changed),
                    ValueError,
                    "excluded generated log",
                )
                # Assert
                assert refused

    def test_missing_real_compiler_script_refused_with_valid_record(self):
        # Arrange
        files = public_wheel_files()
        del files[SCRIPT]
        changed = wheel(files=files)
        # Act
        refused = refusal(
            lambda: self.source_identity(wheel_raw=changed), ValueError, "membership"
        )
        # Assert
        assert refused


def rewrite_wheel_metadata(raw, changes):
    """Create valid newly-recorded artifacts with intentionally different semantics."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        bodies = {name: archive.read(name) for name in archive.namelist()}
    bodies.update(changes)
    record = DIST_INFO + "/RECORD"
    bodies.pop(record)
    bodies[record] = record_bytes(bodies, record)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, body in sorted(bodies.items()):
            item = zipfile.ZipInfo(name)
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(item, body)
    return output.getvalue()


def remove_headers(raw, prefix):
    return b"".join(
        line for line in raw.splitlines(keepends=True) if not line.startswith(prefix)
    )


class GeneratedMetadataTests(unittest.TestCase):
    def test_actual_hatch_source_metadata_with_every_extra_and_entry_group_passes(self):
        # Arrange
        project = tomllib.loads(PYPROJECT.decode())["project"]
        # Act
        result = RELEASE.metadata_source_identity(
            GENERATED_METADATA, GENERATED_METADATA, GENERATED_ENTRY_POINTS, project
        )
        # Assert
        assert result == {
            "runtime_requirements": 35,
            "extras": 3,
            "entry_point_groups": 5,
        }

    def test_missing_runtime_requirements_refused_in_either_artifact(self):
        # Arrange
        bad = remove_headers(GENERATED_METADATA, b"Requires-Dist:")
        for wheel_body, sdist_body in (
            (bad, GENERATED_METADATA),
            (GENERATED_METADATA, bad),
        ):
            with self.subTest(wheel_tampered=wheel_body == bad):
                # Act
                refused = refusal(
                    lambda: RELEASE.metadata_source_identity(
                        wheel_body,
                        sdist_body,
                        GENERATED_ENTRY_POINTS,
                        tomllib.loads(PYPROJECT.decode())["project"],
                    ),
                    ValueError,
                    "runtime requirements",
                )
                # Assert
                assert refused

    def test_weakening_hard_sdk_floor_refused(self):
        # Arrange
        bad = GENERATED_METADATA.replace(b"scitex-sdk>=0.3.1", b"scitex-sdk>=0.0")
        if bad == GENERATED_METADATA:
            raise RuntimeError("weakened SDK fixture did not change source metadata")
        # Act
        refused = refusal(
            lambda: RELEASE.metadata_source_identity(
                bad,
                GENERATED_METADATA,
                GENERATED_ENTRY_POINTS,
                tomllib.loads(PYPROJECT.decode())["project"],
            ),
            ValueError,
            "runtime requirements",
        )
        # Assert
        assert refused

    def test_removing_python_bound_refused_in_both_artifacts(self):
        # Arrange
        bad = remove_headers(GENERATED_METADATA, b"Requires-Python:")
        # Act
        refused = refusal(
            lambda: RELEASE.metadata_source_identity(
                bad,
                bad,
                GENERATED_ENTRY_POINTS,
                tomllib.loads(PYPROJECT.decode())["project"],
            ),
            ValueError,
            "Requires-Python",
        )
        # Assert
        assert refused

    def test_removed_or_normalized_duplicate_extra_refused(self):
        # Arrange
        for bad in (
            remove_headers(GENERATED_METADATA, b"Provides-Extra: docs"),
            GENERATED_METADATA + b"Provides-Extra: Docs\n",
        ):
            with self.subTest(tamper_sha256=hashlib.sha256(bad).hexdigest()):
                # Act
                refused = refusal(
                    lambda: RELEASE.metadata_source_identity(
                        bad,
                        GENERATED_METADATA,
                        GENERATED_ENTRY_POINTS,
                        tomllib.loads(PYPROJECT.decode())["project"],
                    ),
                    ValueError,
                    "extras",
                )
                # Assert
                assert refused

    def test_missing_changed_foreign_and_duplicate_entry_points_refused(self):
        # Arrange
        for bad in (
            b"",
            GENERATED_ENTRY_POINTS.replace(
                b"scitex_writer._cli:main", b"scitex_writer._cli:other"
            ),
            GENERATED_ENTRY_POINTS + b"\n[foreign.group]\nforeign = unknown:main\n",
            GENERATED_ENTRY_POINTS
            + b"\n[console_scripts]\nscitex-writer = unknown:main\n",
        ):
            with self.subTest(tamper_sha256=hashlib.sha256(bad).hexdigest()):
                # Act
                refused = refusal(
                    lambda: RELEASE.metadata_source_identity(
                        GENERATED_METADATA,
                        GENERATED_METADATA,
                        bad,
                        tomllib.loads(PYPROJECT.decode())["project"],
                    ),
                    ValueError,
                )
                # Assert
                assert refused

    def test_rehashed_stripped_wheel_metadata_passes_record_but_source_refuses(self):
        # Arrange
        original, sdist_body = whole_archives()
        altered = rewrite_wheel_metadata(
            original,
            {
                DIST_INFO + "/METADATA": remove_headers(
                    GENERATED_METADATA, b"Requires-Dist:"
                )
            },
        )
        archive_result = RELEASE.wheel_identity(altered, VERSION)
        # Act
        refused = refusal(
            lambda: RELEASE.source_payload_identity(
                altered, sdist_body, SOURCE, REPOSITORY
            ),
            ValueError,
            "runtime requirements",
        )
        # Assert
        assert archive_result["record_members"] > 600 and refused

    def test_fully_source_matched_sdist_with_stripped_python_metadata_refuses(self):
        # Arrange
        original, _ = whole_archives()
        altered = sdist(
            files=public_source_files(),
            metadata_body=remove_headers(GENERATED_METADATA, b"Requires-Python:"),
        )
        RELEASE.sdist_identity(altered, VERSION)
        # Act
        refused = refusal(
            lambda: RELEASE.source_payload_identity(
                original, altered, SOURCE, REPOSITORY
            ),
            ValueError,
            "Requires-Python",
        )
        # Assert
        assert refused

    def test_rehashed_entry_point_tampering_passes_record_but_source_refuses(self):
        # Arrange
        original, sdist_body = whole_archives()
        altered = rewrite_wheel_metadata(
            original,
            {
                DIST_INFO
                + "/entry_points.txt": b"[console_scripts]\nscitex-writer = unknown:main\n"
            },
        )
        RELEASE.wheel_identity(altered, VERSION)
        # Act
        refused = refusal(
            lambda: RELEASE.source_payload_identity(
                altered, sdist_body, SOURCE, REPOSITORY
            ),
            ValueError,
            "entry points",
        )
        # Assert
        assert refused

    def test_unqualified_dist_info_member_refuses_even_with_valid_record(self):
        # Arrange
        original, sdist_body = whole_archives()
        altered = rewrite_wheel_metadata(
            original, {DIST_INFO + "/arbitrary-generated.bin": b"unknown"}
        )
        RELEASE.wheel_identity(altered, VERSION)
        # Act
        refused = refusal(
            lambda: RELEASE.source_payload_identity(
                altered, sdist_body, SOURCE, REPOSITORY
            ),
            ValueError,
            "unqualified generated",
        )
        # Assert
        assert refused

    def test_rehashed_license_source_tampering_refused(self):
        # Arrange
        original, sdist_body = whole_archives()
        altered = rewrite_wheel_metadata(
            original, {DIST_INFO + "/licenses/LICENSE": b"wrong license\n"}
        )
        RELEASE.wheel_identity(altered, VERSION)
        # Act
        refused = refusal(
            lambda: RELEASE.source_payload_identity(
                altered, sdist_body, SOURCE, REPOSITORY
            ),
            ValueError,
            "license source bytes",
        )
        # Assert
        assert refused

    def test_rehashed_nonpure_wheel_declaration_refused(self):
        # Arrange
        original, sdist_body = whole_archives()
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            bad = archive.read(DIST_INFO + "/WHEEL").replace(b"true", b"false")
        altered = rewrite_wheel_metadata(original, {DIST_INFO + "/WHEEL": bad})
        RELEASE.wheel_identity(altered, VERSION)
        # Act
        refused = refusal(
            lambda: RELEASE.source_payload_identity(
                altered, sdist_body, SOURCE, REPOSITORY
            ),
            ValueError,
            "reviewed pure package",
        )
        # Assert
        assert refused

    def test_quote_whitespace_and_conjunction_order_normalize_without_execution(self):
        # Arrange
        first = (
            "example[API]>=2,<3; python_version >= '3.10' and sys_platform == 'linux'"
        )
        second = (
            'Example[api](<3, >=2); sys_platform=="linux" and python_version>="3.10"'
        )
        # Act
        first_identity = RELEASE.requirement_identity(first)
        second_identity = RELEASE.requirement_identity(second)
        # Assert
        assert first_identity == second_identity

    def test_requirement_identity_preserves_name_extra_and_version_parts(self):
        # Arrange
        requirement = "Example[API](<3, >=2); sys_platform == 'linux'"
        # Act
        result = RELEASE.requirement_identity(requirement)
        # Assert
        assert result[:3] == ("example", ("api",), ("<3", ">=2"))

    def test_changed_marker_or_boolean_grouping_is_distinct(self):
        # Arrange
        first = "example; python_version >= '3.10' and sys_platform == 'linux'"
        # Act
        original = RELEASE.requirement_identity(first)
        changed = RELEASE.requirement_identity(first.replace(" and ", " or "))
        # Assert
        assert original != changed

    def test_marker_urls_code_and_unknown_syntax_fail_closed(self):
        # Arrange
        for bad in (
            "example @ https://example.invalid/pkg.whl",
            "example; unknown_variable == 'x'",
            "example; __import__('os')",
            "example; (python_version > '3'",
        ):
            with self.subTest(value=bad):
                # Act
                refused = refusal(lambda: RELEASE.requirement_identity(bad), ValueError)
                # Assert
                assert refused

    def test_source_dynamic_or_cyclic_self_extras_refuse(self):
        # Arrange
        original = tomllib.loads(PYPROJECT.decode())["project"]
        dynamic = {**original, "dynamic": ["dependencies"]}
        cyclic = {**original, "optional-dependencies": {"all": ["scitex-writer[all]"]}}
        for project in (dynamic, cyclic):
            with self.subTest(source_dynamic=bool(project.get("dynamic"))):
                # Act
                refused = refusal(
                    lambda: RELEASE.declared_metadata(project), ValueError
                )
                # Assert
                assert refused

    def test_license_declaration_refuses_missing_changed_and_duplicate_in_either_artifact(
        self,
    ):
        # Arrange
        project = tomllib.loads(PYPROJECT.decode())["project"]
        for bad in (
            remove_headers(GENERATED_METADATA, b"License-File:"),
            GENERATED_METADATA.replace(
                b"License-File: LICENSE", b"License-File: OTHER"
            ),
            GENERATED_METADATA + b"License-File: LICENSE\n",
        ):
            for wheel_body, sdist_body in (
                (bad, GENERATED_METADATA),
                (GENERATED_METADATA, bad),
            ):
                with self.subTest(
                    tamper_sha256=hashlib.sha256(bad).hexdigest(),
                    wheel_tampered=wheel_body == bad,
                ):
                    # Act
                    refused = refusal(
                        lambda: RELEASE.metadata_source_identity(
                            wheel_body, sdist_body, GENERATED_ENTRY_POINTS, project
                        ),
                        ValueError,
                        "license declaration",
                    )
                    # Assert
                    assert refused

    def test_missing_wheel_license_payload_refuses_with_fresh_valid_record(self):
        # Arrange
        original, sdist_body = whole_archives()
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            bodies = {name: archive.read(name) for name in archive.namelist()}
        bodies.pop(DIST_INFO + "/licenses/LICENSE")
        bodies.pop(DIST_INFO + "/RECORD")
        bodies[DIST_INFO + "/RECORD"] = record_bytes(bodies, DIST_INFO + "/RECORD")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, body in sorted(bodies.items()):
                item = zipfile.ZipInfo(name)
                item.create_system = 3
                item.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(item, body)
        altered = buffer.getvalue()
        RELEASE.wheel_identity(altered, VERSION)
        # Act
        refused = refusal(
            lambda: RELEASE.source_payload_identity(
                altered, sdist_body, SOURCE, REPOSITORY
            ),
            ValueError,
            "license payload",
        )
        # Assert
        assert refused

    def test_changed_wheel_version_tag_or_duplicate_header_refuses_with_valid_record(
        self,
    ):
        # Arrange
        original, sdist_body = whole_archives()
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            header = archive.read(DIST_INFO + "/WHEEL")
        for bad in (
            header.replace(b"Wheel-Version: 1.0", b"Wheel-Version: 2.0"),
            header.replace(b"Tag: py3-none-any", b"Tag: cp312-cp312-linux_x86_64"),
            header + b"Root-Is-Purelib: true\n",
        ):
            altered = rewrite_wheel_metadata(original, {DIST_INFO + "/WHEEL": bad})
            RELEASE.wheel_identity(altered, VERSION)
            # Act
            refused = refusal(
                lambda: RELEASE.source_payload_identity(
                    altered, sdist_body, SOURCE, REPOSITORY
                ),
                ValueError,
                "reviewed pure package",
            )
            # Assert
            assert refused


    def test_genuine_current_metadata_25_absent_import_fields_passes(self):
        # Arrange
        project = tomllib.loads(PYPROJECT.decode())["project"]
        # Act
        result = RELEASE.metadata_source_identity(
            GENERATED_METADATA_25,
            GENERATED_METADATA_25,
            GENERATED_ENTRY_POINTS,
            project,
        )
        # Assert
        assert result == {
            "runtime_requirements": 35,
            "extras": 3,
            "entry_point_groups": 5,
        }

    def test_unqualified_metadata_versions_refused_in_either_artifact(self):
        # Arrange
        for replacement in (b"2.6", b"3.0"):
            bad = GENERATED_METADATA_25.replace(
                b"Metadata-Version: 2.5", b"Metadata-Version: " + replacement
            )
            for wheel_body, sdist_body in (
                (bad, GENERATED_METADATA_25), (GENERATED_METADATA_25, bad)
            ):
                with self.subTest(
                    version=replacement, wheel_tampered=wheel_body == bad
                ):
                    # Act
                    refused = refusal(
                        lambda: RELEASE.metadata_source_identity(
                            wheel_body, sdist_body, GENERATED_ENTRY_POINTS,
                            tomllib.loads(PYPROJECT.decode())["project"],
                        ),
                        ValueError,
                        "metadata version",
                    )
                    # Assert
                    assert refused

    def test_duplicate_metadata_version_refused(self):
        # Arrange
        bad = GENERATED_METADATA_25 + b"Metadata-Version: 2.5\n"
        # Act
        refused = refusal(
            lambda: RELEASE.metadata_source_identity(
                bad, bad, GENERATED_ENTRY_POINTS,
                tomllib.loads(PYPROJECT.decode())["project"],
            ),
            ValueError,
            "metadata version",
        )
        # Assert
        assert refused

    def test_unqualified_generated_import_headers_refused_in_either_artifact(self):
        # Arrange
        declarations = (
            b"Import-Name: scitex_writer\n",
            b"Import-Name:\n",
            b"Import-Namespace: scitex\n",
            b"Import-Namespace:\n",
        )
        for declaration in declarations:
            bad = GENERATED_METADATA_25 + declaration
            for wheel_body, sdist_body in (
                (bad, GENERATED_METADATA_25), (GENERATED_METADATA_25, bad)
            ):
                with self.subTest(
                    declaration=declaration, wheel_tampered=wheel_body == bad
                ):
                    # Act
                    refused = refusal(
                        lambda: RELEASE.metadata_source_identity(
                            wheel_body, sdist_body, GENERATED_ENTRY_POINTS,
                            tomllib.loads(PYPROJECT.decode())["project"],
                        ),
                        ValueError,
                        "generated import declarations",
                    )
                    # Assert
                    assert refused

    def test_unqualified_source_import_declarations_refused(self):
        # Arrange
        for key in ("import-names", "import-namespaces"):
            for value in ([], ["scitex_writer"]):
                with self.subTest(key=key, value=value):
                    project = dict(tomllib.loads(PYPROJECT.decode())["project"])
                    project[key] = value
                    # Act
                    refused = refusal(
                        lambda: RELEASE.metadata_source_identity(
                            GENERATED_METADATA_25, GENERATED_METADATA_25,
                            GENERATED_ENTRY_POINTS, project,
                        ),
                        ValueError,
                        "source import declarations",
                    )
                    # Assert
                    assert refused


class ProofAndCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="writer-release-proof-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.wheel_path = self.directory / (SDIST_ROOT + "-py3-none-any.whl")
        self.sdist_path = self.directory / (SDIST_ROOT + ".tar.gz")
        wheel_raw, sdist_raw = whole_archives()
        self.wheel_path.write_bytes(wheel_raw)
        self.sdist_path.write_bytes(sdist_raw)

    def proof(self, **changes):
        arguments = {
            "directory": self.directory,
            "tag": TAG,
            "commit": SOURCE,
            "run": "123456",
            "attempt": "1",
            "source_root": REPOSITORY,
            **changes,
        }
        return RELEASE.artifact_proof(**arguments)

    def cli(self, mode, changes=None, commit=SOURCE, revalidate=False, query=None):
        environment = {
            "PATH": "/usr/bin:/bin",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_RUN_ATTEMPT": "1",
            **(changes or {}),
        }
        arguments = [
            str(HELPER),
            mode,
            "--tag",
            TAG,
            "--commit",
            commit,
            "--dist",
            str(self.directory),
        ]
        if revalidate:
            arguments.append("--revalidate")
        previous = Path.cwd()
        try:
            os.chdir(REPOSITORY)
            with (
                environment_inputs(environment),
                argument_inputs(arguments),
                contextlib.redirect_stdout(io.StringIO()) as captured,
            ):
                RELEASE.main(query=query or QueryFixture({}))
        finally:
            os.chdir(previous)
        return json.loads(captured.getvalue())

    def test_exact_two_actual_source_archives_have_bound_proof(self):
        # Arrange
        # Act
        proof = self.proof()
        result = (proof["tag"], proof["commit"], proof["run"], len(proof["files"]))
        # Assert
        assert result == (TAG, SOURCE, "123456", 2)

    def test_extra_hidden_or_regular_artifact_refused(self):
        # Arrange
        for name in ("extra.txt", ".hidden"):
            with self.subTest(name=name):
                path = self.directory / name
                path.write_bytes(b"synthetic extra artifact")
                try:
                    # Act
                    refused = refusal(lambda: self.proof(), ValueError)
                    # Assert
                    assert refused
                finally:
                    path.unlink()

    def test_symlink_artifact_refused(self):
        # Arrange
        with tempfile.TemporaryDirectory(prefix="writer-retained-wheel-") as retained:
            target = Path(retained) / self.wheel_path.name
            self.wheel_path.rename(target)
            self.wheel_path.symlink_to(target)
            # Act
            refused = refusal(lambda: self.proof(), ValueError, "regular file")
            # Assert
            assert refused

    def test_symlink_artifact_directory_refused(self):
        # Arrange
        link = self.directory / "dist-link"
        link.symlink_to(self.directory, target_is_directory=True)
        # Act
        refused = refusal(lambda: self.proof(directory=link), ValueError)
        # Assert
        assert refused

    def test_malformed_source_run_or_attempt_refused(self):
        # Arrange
        for change in ({"commit": "not-a-sha"}, {"run": "run;escape"}, {"attempt": ""}):
            with self.subTest(change=change):
                # Act
                refused = refusal(lambda: self.proof(**change), ValueError)
                # Assert
                assert refused

    def test_real_write_and_verify_proof_positive(self):
        # Arrange
        written = self.cli("write-proof")
        # Act
        result = self.cli("verify-proof")
        # Assert
        assert result == written

    def test_stale_run_and_attempt_proof_refused(self):
        # Arrange
        self.cli("write-proof")
        for changed in ({"GITHUB_RUN_ID": "999999"}, {"GITHUB_RUN_ATTEMPT": "2"}):
            with self.subTest(changed=changed):
                # Act
                refused = refusal(
                    lambda: self.cli("verify-proof", changed), ValueError, "proof"
                )
                # Assert
                assert refused

    def test_stale_source_proof_refused(self):
        # Arrange
        self.cli("write-proof")
        path = self.directory / RELEASE.PROOF
        value = json.loads(path.read_bytes())
        value["commit"] = "a" * 40
        path.write_text(json.dumps(value))
        # Act
        refused = refusal(lambda: self.cli("verify-proof"), ValueError, "proof")
        # Assert
        assert refused

    def test_actual_checkout_must_equal_declared_release_commit(self):
        # Arrange
        # Act
        refused = refusal(
            lambda: self.cli("write-proof", commit="a" * 40),
            ValueError,
            "checkout and release commit",
        )
        # Assert
        assert refused

    def test_existing_proof_is_not_overwritten(self):
        # Arrange
        self.cli("write-proof")
        # Act
        refused = refusal(lambda: self.cli("write-proof"), FileExistsError)
        # Assert
        assert refused

    def test_final_publisher_revalidation_accepts_same_existing_tag(self):
        # Arrange
        written = self.cli("write-proof")
        environment = {
            "GITHUB_REPOSITORY": RELEASE.REPOSITORY,
            "GITHUB_ACTOR": "fixture-member",
            "GITHUB_TRIGGERING_ACTOR": "fixture-member",
        }
        with environment_inputs({}):
            # Act
            result = self.cli(
                "verify-proof",
                environment,
                revalidate=True,
                query=QueryFixture(admitted_routes()),
            )
            # Assert
            assert result == written

    def test_final_publisher_revalidation_refuses_retargeted_tag(self):
        # Arrange
        self.cli("write-proof")
        changed_source = "a" * 40
        values = admitted_routes()
        values[PREFIX + "/git/ref/tags/" + TAG, 200]["object"]["sha"] = changed_source
        values[PREFIX + "/compare/" + changed_source + "...main", 200] = {
            "base_commit": {"sha": changed_source},
            "status": "ahead",
        }
        values[PREFIX + "/contents/pyproject.toml?ref=" + changed_source, 200] = values[
            PREFIX + "/contents/pyproject.toml?ref=" + SOURCE, 200
        ]
        environment = {
            "GITHUB_REPOSITORY": RELEASE.REPOSITORY,
            "GITHUB_ACTOR": "fixture-member",
            "GITHUB_TRIGGERING_ACTOR": "fixture-member",
        }
        with environment_inputs({}):
            # Act
            refused = refusal(
                lambda: self.cli(
                    "verify-proof",
                    environment,
                    revalidate=True,
                    query=QueryFixture(values),
                ),
                ValueError,
                "release tag identity changed",
            )
            # Assert
            assert refused

    def test_coordinated_wheel_body_and_record_tampering_after_proof_refused(self):
        # Arrange
        self.cli("write-proof")
        files = public_wheel_files()
        files[CONFIG] += b"\n# changed\n"
        self.wheel_path.write_bytes(wheel(files=files))
        # Act
        refused = refusal(
            lambda: self.cli("verify-proof"), ValueError, "public source bytes"
        )
        # Assert
        assert refused

    def test_sdist_body_tampering_after_proof_refused(self):
        # Arrange
        self.cli("write-proof")
        files = dict(public_source_files())
        files["src/" + CONFIG] += b"\n# changed\n"
        self.sdist_path.write_bytes(sdist(files=files))
        # Act
        refused = refusal(
            lambda: self.cli("verify-proof"), ValueError, "public source bytes"
        )
        # Assert
        assert refused


# Finite real Bash lifecycle controls; scientific/install/OIDC children are fixtures.
DRIVER_SOURCE = HERE
DRIVER_PYTHON = sys.executable

DRIVER_STUB = r"""from pathlib import Path
import json,os,sys,time
a=sys.argv[1:]
name=Path(sys.argv[0]).name
body=sys.stdin.read() if a and a[0]=='-' else ''
stage='uv' if name=='uv' else ('pytest' if a[:2]==['-m','pytest'] else 'twine' if a[:2]==['-m','twine'] else 'build' if a[:2]==['-m','build'] else 'mint' if body else 'proof-first' if 'verify-proof' in a and '--revalidate' in a else 'proof-final' if 'verify-proof' in a else 'python')
root=Path(os.environ['TMPDIR'])
with open(os.environ['FIXTURE_LOG'],'a') as f:
 f.write(json.dumps({'stage':stage,'root':str(root),'minted_fixture_only':os.environ.get('TWINE_PASSWORD')=='fixture-token'})+'\n')
if os.environ.get('REPLACE_STAGE')==stage:
 displaced=root.with_name(root.name+'-displaced')
 root.rename(displaced)
 if os.environ.get('REPLACE_SYMLINK')=='1':root.symlink_to(os.environ['UNRELATED'],target_is_directory=True)
 else:root.mkdir(mode=0o700)
if os.environ.get('BLOCK_STAGE')==stage:
 Path(os.environ['BLOCK_READY']).write_text(str(root))
 time.sleep(20)
if os.environ.get('FAIL_STAGE')==stage:sys.exit(37)
if name=='uv':sys.exit(0)
if a==['-V']:print('Python fixture');sys.exit(0)
if a[:2]==['-c','import matplotlib']:sys.exit(1)
if stage=='build':
 Path('dist').mkdir();Path('dist/fixture.whl').write_bytes(b'fixture');Path('dist/fixture.tar.gz').write_bytes(b'fixture')
if stage=='mint':print('fixture-token')
"""


class DriverCleanup(unittest.TestCase):
    receipts = []

    def exercise(self, name, mode="success"):
        with tempfile.TemporaryDirectory(
            prefix="writer-driver-fixture-", dir=os.environ.get("TMPDIR")
        ) as directory:
            fixture = Path(directory)
            bin_dir = fixture / "fake-bin"
            bin_dir.mkdir()
            for executable in ("python", "uv"):
                path = bin_dir / executable
                path.write_text("#!" + DRIVER_PYTHON + "\n" + DRIVER_STUB)
                path.chmod(0o700)
            source_path = DRIVER_SOURCE / name
            source = source_path.read_text()
            # Only fixed interpreter/priority tool paths are routed to finite fake children.
            source = source.replace("/opt/venv-$V", str(bin_dir))
            source = source.replace("$VENV/bin/python", str(bin_dir / "python"))
            source = source.replace("$VENV/bin:", str(bin_dir) + ":")
            source = source.replace(
                'PY="' + str(bin_dir) + '/bin/python"',
                'PY="' + str(bin_dir / "python") + '"',
            )
            source = source.replace(str(bin_dir) + "/bin:", str(bin_dir) + ":")
            minted_log = fixture / "mint-cleared"
            source = source.replace(
                "set -euo pipefail",
                'unset() { builtin unset "$@"; if [[ "${1-}" = MINTED ]] && ! declare -p MINTED >/dev/null 2>&1; then printf \'cleared\\n\' >> "$MINT_CLEAR_LOG"; fi; }\nset -euo pipefail',
                1,
            )
            driver = fixture / name
            driver.write_text(source)
            work = fixture / "work"
            work.mkdir()
            if name == "publish-in-sif.sh":
                (work / "dist").mkdir()
                for member in ("fixture.whl", "fixture.tar.gz"):
                    (work / "dist" / member).write_bytes(b"fixture")
            unrelated = fixture / "preexisting-unrelated"
            unrelated.mkdir()
            sentinel = unrelated / "preserve"
            sentinel.write_bytes(b"unchanged")
            log, ready = fixture / "children.jsonl", fixture / "ready"
            phase = {
                "run-in-sif.sh": "pytest",
                "build-in-sif.sh": "build",
                "publish-in-sif.sh": "twine",
            }[name]
            env = {
                "PATH": str(bin_dir) + ":/usr/bin:/bin",
                "HOME": str(fixture),
                "LANG": "C.UTF-8",
                "GITHUB_RUN_ID": "7000001",
                "GITHUB_RUN_ATTEMPT": "1",
                "RELEASE_TAG": "v0.0.0",
                "RELEASE_COMMIT": "0" * 40,
                "FIXTURE_LOG": str(log),
                "BLOCK_READY": str(ready),
                "MINT_CLEAR_LOG": str(minted_log),
                "TMPDIR": str(unrelated),
                "UNRELATED": str(unrelated),
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "fixture-only",
                "ACTIONS_ID_TOKEN_REQUEST_URL": "fixture-only",
                "PUBLISH_PYTHON": str(bin_dir / "python"),
            }
            if mode == "nonzero":
                env["FAIL_STAGE"] = phase
            elif mode == "install-failure":
                env["FAIL_STAGE"] = "uv"
            elif mode in (
                "term",
                "interrupt-mint",
                "interrupt-first-proof",
                "term-first-proof-shell",
                "int-first-proof-shell",
            ):
                env["BLOCK_STAGE"] = (
                    "mint"
                    if mode == "interrupt-mint"
                    else "proof-first"
                    if mode
                    in (
                        "interrupt-first-proof",
                        "term-first-proof-shell",
                        "int-first-proof-shell",
                    )
                    else phase
                )
            elif mode in ("mint-failure", "proof-failure", "first-proof-failure"):
                env["FAIL_STAGE"] = (
                    "mint"
                    if mode == "mint-failure"
                    else "proof-first"
                    if mode == "first-proof-failure"
                    else "proof-final"
                )
            elif mode in ("replacement", "symlink"):
                env["REPLACE_STAGE"] = phase
                env["REPLACE_SYMLINK"] = "1" if mode == "symlink" else "0"
            started = time.monotonic()
            child = subprocess.Popen(
                ["/bin/bash", str(driver), "3.12"],
                cwd=work,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                if mode in (
                    "term",
                    "interrupt-mint",
                    "interrupt-first-proof",
                    "term-first-proof-shell",
                    "int-first-proof-shell",
                ):
                    deadline = time.monotonic() + 3
                    while (
                        not ready.exists()
                        and child.poll() is None
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    self.assertTrue(
                        ready.exists(), "real finite child must reach interrupted stage"
                    )
                    os.kill(
                        child.pid,
                        signal.SIGINT
                        if mode == "int-first-proof-shell"
                        else signal.SIGTERM,
                    ) if mode.endswith("-shell") else os.killpg(
                        child.pid, signal.SIGTERM
                    )
                stdout, stderr = child.communicate(timeout=4)
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.communicate()
            rows = (
                [json.loads(line) for line in log.read_text().splitlines()]
                if log.exists()
                else []
            )
            roots = {
                Path(row["root"])
                for row in rows
                if Path(row["root"]).parent == Path("/tmp")
                and Path(row["root"]).name.startswith(
                    name.split("-")[0].replace("run", "ci")
                    + "-scitex_writer-7000001-1-3.12-"
                )
            }
            self.assertTrue(
                roots, "actual driver child must expose reserved scratch metadata"
            )
            self.assertEqual(len(roots), 1)
            root = roots.pop()
            try:
                expected = (
                    130
                    if mode == "int-first-proof-shell"
                    else 143
                    if mode
                    in (
                        "term",
                        "interrupt-mint",
                        "interrupt-first-proof",
                        "term-first-proof-shell",
                        "int-first-proof-shell",
                    )
                    else 37
                    if mode
                    in (
                        "nonzero",
                        "install-failure",
                        "mint-failure",
                        "proof-failure",
                        "first-proof-failure",
                    )
                    else 1
                    if mode in ("replacement", "symlink")
                    else 0
                )
                self.assertEqual(
                    child.returncode, expected, stderr.decode(errors="replace")
                )
                self.assertEqual(sentinel.read_bytes(), b"unchanged")
                if mode in ("replacement", "symlink"):
                    self.assertTrue(
                        root.exists(), "replacement must be refused rather than deleted"
                    )
                    self.assertIn(b"cleanup refused or failed", stderr)
                else:
                    self.assertFalse(
                        root.exists(),
                        "exclusive owned scratch must be removed on every exit",
                    )
                if name == "publish-in-sif.sh":
                    self.assertTrue(
                        minted_log.exists(),
                        "actual builtin unset must run on every exit",
                    )
                    if mode == "success":
                        self.assertTrue(
                            any(
                                row["stage"] == "twine" and row["minted_fixture_only"]
                                for row in rows
                            )
                        )
                self.receipts.append(
                    {
                        "driver": name,
                        "mode": mode,
                        "exit": child.returncode,
                        "elapsed_s": round(time.monotonic() - started, 4),
                        "source_sha256": hashlib.sha256(
                            source_path.read_bytes()
                        ).hexdigest(),
                        "unrelated_preserved": True,
                        "scratch_absent": not root.exists(),
                        "fake_children_only": True,
                        "signal_scope": "owner shell PID only"
                        if mode.endswith("-shell")
                        else "owned process group"
                        if mode
                        in (
                            "term",
                            "interrupt-mint",
                            "interrupt-first-proof",
                            "term-first-proof-shell",
                            "int-first-proof-shell",
                        )
                        else None,
                    }
                )
            finally:
                # Fixture-only cleanup includes deliberately displaced/replacement scratch.
                for path in (root, root.with_name(root.name + "-displaced")):
                    if path.is_symlink():
                        path.unlink()
                    elif path.exists():
                        import shutil

                        shutil.rmtree(path)

    def test_run_removes_exclusive_scratch(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, "success")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_run_preserves_failure_status(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, "nonzero")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_run_install_failure(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, "install-failure")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_run_terminates_owned_children(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, "term")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_run_preserves_replaced_scratch(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, "replacement")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_run_refuses_foreign_scratch(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, "symlink")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_removes_exclusive_scratch(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, "success")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_preserves_failure_status(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, "nonzero")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_install_failure(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, "install-failure")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_terminates_owned_children(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, "term")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_preserves_replaced_scratch(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, "replacement")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_refuses_foreign_scratch(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, "symlink")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_removes_exclusive_scratch(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "success")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_preserves_failure_status(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "nonzero")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_install_failure(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "install-failure")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_terminates_owned_children(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "term")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_preserves_replaced_scratch(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "replacement")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_refuses_foreign_scratch(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "symlink")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_mint_failure(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "mint-failure")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_proof_failure(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "proof-failure")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_interrupt_mint(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "interrupt-mint")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_first_proof_failure(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "first-proof-failure")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_interrupt_first_proof(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "interrupt-first-proof")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_term_first_proof_shell(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "term-first-proof-shell")
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_int_first_proof_shell(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, "int-first-proof-shell")
        # Assert
        assert self.receipts[-1]["driver"] == driver


DRIVER_CHILD = r"""from pathlib import Path
import json,os,signal,sys,time
base=Path(os.environ['FIXTURE_PARENT']);root=Path(os.environ['TMPDIR'])
def metadata():
 raw=Path('/proc/self/stat').read_text().rsplit(') ',1)[1].split()
 return {'pid':os.getpid(),'fixture_birth':raw[19],'pgrp':int(raw[2]),'ppid':os.getppid()}
signal.signal(signal.SIGINT,signal.default_int_handler)
(base/'foreground.json').write_text(json.dumps(metadata()))
if os.environ['STUBBORN']=='1':
 pid=os.fork()
 if pid==0:
  signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN)
  if os.environ.get('LEAK_SUCCESS')=='1':
   fd=os.open('/dev/null',os.O_WRONLY);os.dup2(fd,1);os.dup2(fd,2);os.close(fd)
  with (root/'grandchild-held-file').open('w') as held:
   held.write('fixture');held.flush()
   (base/'grandchild.json').write_text(json.dumps(metadata()))
   time.sleep(20)
  os._exit(0)
 while not (base/'grandchild.json').exists():time.sleep(.005)
(base/'ready').write_text('ready')
if os.environ.get('LEAK_SUCCESS')=='1':
 while not (base/'release-normal').exists():time.sleep(.005)
 sys.exit(0)
time.sleep(20)
"""
DRIVER_REMOVER = r"""from pathlib import Path
import json,os,sys
base=Path(os.environ['FIXTURE_PARENT']);p=base/'grandchild.json';live=False
if p.exists():
 old=json.loads(p.read_text());s=Path('/proc')/str(old['pid'])/'stat'
 if s.exists():
  raw=s.read_text().rsplit(') ',1)[1].split();live=raw[19]==old['fixture_birth'] and raw[0]!='Z'
(base/'removal-witness.json').write_text(json.dumps({'grandchild_live_before_rm':live}))
os.execv('/usr/bin/rm',['/usr/bin/rm',*sys.argv[1:]])
"""


def fixture_birth(metadata):
    try:
        raw = (
            (Path("/proc") / str(metadata["pid"]) / "stat")
            .read_text()
            .rsplit(") ", 1)[1]
            .split()
        )
    except FileNotFoundError:
        return None
    return raw[19], raw[0]


def fixture_reap(metadata):
    try:
        os.waitpid(metadata["pid"], os.WNOHANG)
    except ChildProcessError:
        pass


class ShellCancellation(unittest.TestCase):
    receipts = []

    @classmethod
    def setUpClass(cls):
        cls._libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        if cls._libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:
            raise RuntimeError("fixture subreaper state could not be read")
        cls._previous_subreaper = previous.value
        if cls._libc.prctl(36, 1, 0, 0, 0) != 0:
            raise RuntimeError("fixture subreaper could not be enabled")

    @classmethod
    def tearDownClass(cls):
        if cls._libc.prctl(36, cls._previous_subreaper, 0, 0, 0) != 0:
            raise RuntimeError("fixture subreaper state could not be restored")

    def exercise(self, name, signum, stubborn):
        source = (DRIVER_SOURCE / name).read_text()
        start = source.index("# BEGIN owned temporary-root lifecycle")
        end = source.index("driver_body() {", start)
        # Use the entire actual lifecycle plus allocation; only rm is instrumented.
        lifecycle = source[start:end]
        with tempfile.TemporaryDirectory(
            prefix="shell-signal-fixture-", dir=os.environ.get("TMPDIR")
        ) as directory:
            fixture = Path(directory)
            child_script, remover = fixture / "finite-child.py", fixture / "remover"
            child_script.write_text(DRIVER_CHILD)
            remover.write_text("#!" + DRIVER_PYTHON + "\n" + DRIVER_REMOVER)
            remover.chmod(0o700)
            lifecycle = lifecycle.replace("/usr/bin/rm ", str(remover) + " ")
            script = fixture / "driver.sh"
            script.write_text(
                'set -euo pipefail\nSCRATCH_PREFIX="/tmp/ci-scitex_writer-7000002-1-3.12-"\n'
                + lifecycle
                + '\nprintf "%s" "$TMPDIR" > "$FIXTURE_PARENT/root"\n'
                + '\ndriver_body() {\nprintf "%s" "$BASHPID" > "$FIXTURE_PARENT/body-pid"\n'
                + '"$FIXTURE_PYTHON" -I -S "$FIXTURE_PARENT/finite-child.py"\n}\nrun_owned_body\n'
            )
            env = {
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "FIXTURE_PARENT": str(fixture),
                "FIXTURE_PYTHON": DRIVER_PYTHON,
                "STUBBORN": "1" if stubborn else "0",
            }
            if signum is None:
                env["LEAK_SUCCESS"] = "1"
            unrelated = subprocess.Popen(
                ["/usr/bin/sleep", "20"], start_new_session=True
            )
            owner = subprocess.Popen(
                ["/bin/bash", str(script)],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            records, root, stalled = [], None, False
            stop_reaper = threading.Event()
            reaper = None
            started = time.monotonic()
            try:
                deadline = time.monotonic() + 3
                while (
                    not (fixture / "ready").exists()
                    and owner.poll() is None
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                self.assertTrue(
                    (fixture / "ready").exists(),
                    "actual foreground/descendant must be ready",
                )
                records = [json.loads((fixture / "foreground.json").read_text())]
                if stubborn:
                    records.append(
                        json.loads((fixture / "grandchild.json").read_text())
                    )
                body_pid = int((fixture / "body-pid").read_text())
                body_raw = (
                    (Path("/proc") / str(body_pid) / "stat")
                    .read_text()
                    .rsplit(") ", 1)[1]
                    .split()
                )
                body = {
                    "pid": body_pid,
                    "fixture_birth": body_raw[19],
                    "pgrp": int(body_raw[2]),
                }
                self.assertEqual(body["pid"], body["pgrp"])
                self.assertTrue(all(item["pgrp"] == body["pid"] for item in records))
                root = Path((fixture / "root").read_text())

                def adopt_fixture_children():
                    while not stop_reaper.is_set():
                        for item in records:
                            fixture_reap(item)
                        # Reap only adopted descendants in this exact owned group.
                        # The owner's cancellation trap can create a new sleep child.
                        children = (
                            Path("/proc/self/task") / str(os.getpid()) / "children"
                        )
                        for raw_pid in children.read_text().split():
                            try:
                                state = (
                                    (Path("/proc") / raw_pid / "stat")
                                    .read_text()
                                    .rsplit(") ", 1)[1]
                                    .split()
                                )
                                if (
                                    int(state[1]) == os.getpid()
                                    and int(state[2]) == body_pid
                                ):
                                    os.waitpid(int(raw_pid), os.WNOHANG)
                            except (FileNotFoundError, ChildProcessError):
                                pass
                        time.sleep(0.005)

                reaper = threading.Thread(target=adopt_fixture_children, daemon=True)
                reaper.start()
                # This sends to ONLY the owning shell PID, never its process group.
                if signum is None:
                    (fixture / "release-normal").write_text("release")
                else:
                    os.kill(owner.pid, signum)
                try:
                    stdout, stderr = owner.communicate(timeout=4)
                except subprocess.TimeoutExpired:
                    stalled = True
                    for item in records:
                        observed = fixture_birth(item)
                        if (
                            observed
                            and observed[0] == item["fixture_birth"]
                            and observed[1] != "Z"
                        ):
                            os.kill(item["pid"], signal.SIGKILL)
                    stdout, stderr = owner.communicate(timeout=2)
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    for item in records:
                        fixture_reap(item)
                    if all(fixture_birth(item) is None for item in records):
                        break
                    time.sleep(0.01)
                if signum is None:
                    self.assertEqual(owner.returncode, 1)
                    self.assertIn(b"owned child group remains", stderr)
                    self.assertFalse(
                        (fixture / "removal-witness.json").exists(),
                        "live group must prevent rm entirely",
                    )
                    self.assertTrue(root.exists())
                    self.assertTrue(
                        fixture_birth(records[-1])
                        and fixture_birth(records[-1])[1] != "Z"
                    )
                    self.assertIsNone(unrelated.poll())
                    self.receipts.append(
                        {
                            "driver": name,
                            "ordinary_success_with_live_grandchild": "refused",
                            "exit": 1,
                            "elapsed_s": round(time.monotonic() - started, 4),
                            "source_sha256": hashlib.sha256(
                                (DRIVER_SOURCE / name).read_bytes()
                            ).hexdigest(),
                            "rm_called": False,
                            "scratch_preserved": True,
                            "grandchild_still_live_at_refusal": True,
                            "fixture_only_final_cleanup": True,
                        }
                    )
                    return
                witness = json.loads((fixture / "removal-witness.json").read_text())
                self.assertFalse(
                    stalled,
                    "stubborn descendant kept fixture pipes alive after cancellation",
                )
                self.assertEqual(
                    owner.returncode,
                    130 if signum == signal.SIGINT else 143,
                    stderr.decode(errors="replace"),
                )
                self.assertFalse(
                    witness["grandchild_live_before_rm"],
                    "scratch removal must follow descendant termination",
                )
                self.assertIsNone(
                    unrelated.poll(), "unrelated process must remain untouched"
                )
                self.assertFalse(
                    (Path("/proc") / str(body_pid)).exists(),
                    "actual owned body is reaped",
                )
                for item in records:
                    self.assertIsNone(
                        fixture_birth(item),
                        "fixture foreground and adopted grandchild must be reaped",
                    )
                if root is not None:
                    self.assertFalse(root.exists())
                self.receipts.append(
                    {
                        "driver": name,
                        "signal": "INT" if signum == signal.SIGINT else "TERM",
                        "signal_target": "owner shell PID only",
                        "stubborn_grandchild": stubborn,
                        "exit": owner.returncode,
                        "elapsed_s": round(time.monotonic() - started, 4),
                        "body": body,
                        "fixture_children": records,
                        "all_reaped": True,
                        "grandchild_live_at_rm": False,
                        "unrelated_process_preserved": True,
                        "source_sha256": hashlib.sha256(
                            (DRIVER_SOURCE / name).read_bytes()
                        ).hexdigest(),
                    }
                )
            finally:
                stop_reaper.set()
                if reaper is not None:
                    reaper.join(timeout=1)
                if owner.poll() is None:
                    os.kill(owner.pid, signal.SIGKILL)
                    owner.wait(timeout=5)
                for item in records:
                    observed = fixture_birth(item)
                    if (
                        observed
                        and observed[0] == item["fixture_birth"]
                        and observed[1] != "Z"
                    ):
                        os.kill(item["pid"], signal.SIGKILL)
                    fixture_reap(item)
                if root is not None and root.exists():
                    import shutil

                    shutil.rmtree(root)
                unrelated.terminate()
                unrelated.wait(timeout=5)

    def test_run_live_group_refuses_rm(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, None, True)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_run_term_foreground(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGTERM, False)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_run_term_grandchild(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGTERM, True)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_run_int_foreground(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGINT, False)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_run_int_grandchild(self):
        # Arrange
        driver = "run-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGINT, True)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_live_group_refuses_rm(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, None, True)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_term_foreground(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGTERM, False)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_term_grandchild(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGTERM, True)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_int_foreground(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGINT, False)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_build_int_grandchild(self):
        # Arrange
        driver = "build-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGINT, True)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_live_group_refuses_rm(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, None, True)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_term_foreground(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGTERM, False)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_term_grandchild(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGTERM, True)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_int_foreground(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGINT, False)
        # Assert
        assert self.receipts[-1]["driver"] == driver

    def test_publish_int_grandchild(self):
        # Arrange
        driver = "publish-in-sif.sh"
        # Act
        self.exercise(driver, signal.SIGINT, True)
        # Assert
        assert self.receipts[-1]["driver"] == driver


if __name__ == "__main__":
    unittest.main(verbosity=2)

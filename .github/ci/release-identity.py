#!/usr/bin/env python3
"""Bind a Writer release to one tag, source commit and two verified artifacts."""

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import signal
import stat
import subprocess
import tarfile
import urllib.request
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

import tomllib

REPOSITORY = "scitex-ai/scitex-writer"
TAG = re.compile(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
SHA = re.compile(r"[0-9a-f]{40}")
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
PROOF = "release-proof.json"


def api(path, status=200, *, open_url=urllib.request.urlopen):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request("https://api.github.com/" + path, headers=headers)
    with open_url(request, timeout=10) as response:
        if response.status != status:
            raise ValueError("GitHub identity response did not match")
        if status == 204:
            return {"status": 204}
        body = response.read(1048577)
        if len(body) > 1048576:
            raise ValueError("GitHub identity response too large")
        return json.loads(body)


def member_admission(query=api):
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("release repository does not match")
    actors = {
        os.environ.get("GITHUB_ACTOR", ""),
        os.environ.get("GITHUB_TRIGGERING_ACTOR", ""),
    }
    if not actors or any(not LOGIN.fullmatch(actor) for actor in actors):
        raise ValueError("release actor is missing or malformed")
    for actor in actors:
        if query("orgs/scitex-ai/public_members/" + actor, status=204) != {
            "status": 204
        }:
            raise ValueError("organization membership is not confirmed")


def resolve(tag, query=api):
    if not TAG.fullmatch(tag):
        raise ValueError("release requires an existing vX.Y.Z tag")
    prefix = "repos/" + REPOSITORY
    ref = query(prefix + "/git/ref/tags/" + tag)
    if ref.get("ref") != "refs/tags/" + tag:
        raise ValueError("returned tag ref differs")
    item = ref["object"]
    seen = set()
    for _ in range(5):
        digest = item.get("sha", "")
        if not SHA.fullmatch(digest) or digest in seen:
            raise ValueError("invalid or cyclic tag object")
        seen.add(digest)
        if item.get("type") == "commit":
            break
        if item.get("type") != "tag":
            raise ValueError("tag does not resolve to a commit")
        item = query(prefix + "/git/tags/" + digest)["object"]
    else:
        raise ValueError("tag annotation depth exceeded")
    commit = item["sha"]
    comparison = query(prefix + "/compare/" + commit + "...main")
    if comparison.get("base_commit", {}).get("sha") != commit or comparison.get(
        "status"
    ) not in {"ahead", "identical"}:
        raise ValueError("release source has not been promoted to main")
    content = query(prefix + "/contents/pyproject.toml?ref=" + commit)
    if content.get("encoding") != "base64":
        raise ValueError("unsupported metadata encoding")
    raw = base64.b64decode(content["content"].replace("\n", ""), validate=True)
    if len(raw) > 131072 or hashlib.sha1(
        b"blob " + str(len(raw)).encode() + b"\0" + raw
    ).hexdigest() != content.get("sha"):
        raise ValueError("release metadata Git identity differs")
    project = tomllib.loads(raw.decode())["project"]
    if (
        project["name"].replace("_", "-").lower() != "scitex-writer"
        or project["version"] != tag[1:]
    ):
        raise ValueError("tag and project metadata differ")
    return {"tag": tag, "commit": commit, "version": tag[1:]}


def regular_bytes(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("artifact must be a regular file")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > 268435456:
            raise ValueError("artifact type or size is invalid")
        raw = stream.read()
        after = os.fstat(stream.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) or path.lstat().st_ino != before.st_ino:
        raise ValueError("artifact changed while reading")
    return raw


def safe_member(name):
    path = PurePosixPath(name)
    if (
        "\\" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
    ):
        raise ValueError("unsafe archive member")


def metadata_identity(raw, version):
    message = BytesParser().parsebytes(raw)
    if message.get_all("Name") != ["scitex-writer"] and message.get_all("Name") != [
        "scitex_writer"
    ]:
        raise ValueError("artifact distribution differs")
    if message.get_all("Version") != [version]:
        raise ValueError("artifact version differs")


def wheel_identity(raw, version):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 20000:
            raise ValueError("duplicate or excessive wheel members")
        for item in archive.infolist():
            safe_member(item.filename)
            mode = stat.S_IFMT(item.external_attr >> 16)
            if mode not in {0, stat.S_IFREG, stat.S_IFDIR} or item.file_size > 67108864:
                raise ValueError("unsupported wheel member")
        if sum(item.file_size for item in archive.infolist()) > 1073741824:
            raise ValueError("wheel expanded size exceeded")
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        records = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(metadata) != 1 or len(records) != 1:
            raise ValueError("wheel metadata identity is ambiguous")
        metadata_identity(archive.read(metadata[0]), version)
        record = records[0]
        owner = "scitex_writer-" + version + ".dist-info"
        if metadata[0] != owner + "/METADATA" or record != owner + "/RECORD":
            raise ValueError("wheel metadata and RECORD owners differ")
        seen = set()
        for name, digest, size in csv.reader(
            io.StringIO(archive.read(record).decode())
        ):
            if name in seen or name not in names:
                raise ValueError("wheel RECORD membership differs")
            seen.add(name)
            if name == record:
                if digest or size:
                    raise ValueError("wheel RECORD self entry differs")
                continue
            body = archive.read(name)
            expected = "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(body).digest()
            ).decode().rstrip("=")
            if digest != expected or size != str(len(body)):
                raise ValueError("wheel RECORD hash or size differs")
        if seen != set(names):
            raise ValueError("wheel has unrecorded members")
        key = "scitex_writer/scripts/shell/modules/check_dependancy_commands.sh"
        if (
            key not in names
            or "scitex_writer/_dataclasses/config/__init__.py" not in names
        ):
            raise ValueError("wheel lost required public payload")
        return {"members": len(names), "record_members": len(seen)}


def sdist_identity(raw, version):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        entries = archive.getmembers()
        names = [item.name for item in entries]
        if len(names) != len(set(names)) or len(names) > 20000:
            raise ValueError("duplicate or excessive sdist members")
        for item in entries:
            safe_member(item.name)
            if not (item.isfile() or item.isdir()) or item.size > 67108864:
                raise ValueError("unsupported sdist member")
        if sum(item.size for item in entries) > 1073741824:
            raise ValueError("sdist expanded size exceeded")
        roots = {PurePosixPath(name).parts[0] for name in names}
        if len(roots) != 1:
            raise ValueError("sdist has multiple roots")
        root = next(iter(roots))
        required = {
            root + "/src/scitex_writer/_dataclasses/config/__init__.py",
            root + "/scripts/shell/modules/check_dependancy_commands.sh",
            root + "/PKG-INFO",
            root + "/pyproject.toml",
        }
        if not required.issubset(names) or any(
            not archive.getmember(name).isfile() for name in required
        ):
            raise ValueError("sdist lost required public payload")
        metadata_identity(archive.extractfile(root + "/PKG-INFO").read(), version)
        project = tomllib.loads(
            archive.extractfile(root + "/pyproject.toml").read().decode()
        )["project"]
        if (
            project["version"] != version
            or project["name"].replace("_", "-").lower() != "scitex-writer"
        ):
            raise ValueError("sdist project identity differs")
        return {"members": len(entries)}


def git_read(argv, source_root, stdin=None):
    process = subprocess.Popen(
        ["git", "-C", str(source_root), *argv],
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, _ = process.communicate(stdin, timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise ValueError("public source read timed out") from None
    if process.returncode:
        raise ValueError("public source Git read failed")
    return stdout


def source_payload_identity(wheel_raw, sdist_raw, commit, source_root=Path(".")):
    """Compare public payload membership and bytes with this exact Git commit."""
    if not SHA.fullmatch(commit):
        raise ValueError("public source commit is malformed")
    rows = git_read(["ls-tree", "-r", "-z", "--full-tree", commit], source_root).split(
        b"\0"
    )
    entries = {}
    for row in filter(None, rows):
        metadata, path_raw = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        path = path_raw.decode()
        safe_member(path)
        if path in entries or kind != "blob" or not SHA.fullmatch(oid):
            raise ValueError("public source tree is ambiguous")
        entries[path] = (mode, oid)
    if len(entries) > 20000:
        raise ValueError("public source tree exceeds bounds")
    ids = sorted({oid for _, oid in entries.values()})
    frames = (
        git_read(
            ["cat-file", "--batch-check"], source_root, ("\n".join(ids) + "\n").encode()
        )
        .decode()
        .splitlines()
    )
    if len(frames) != len(ids):
        raise ValueError("public source size inventory differs")
    sizes = []
    for oid, frame in zip(ids, frames, strict=True):
        values = frame.split()
        if (
            len(values) != 3
            or values[:2] != [oid, "blob"]
            or not values[2].isdigit()
            or int(values[2]) > 67108864
        ):
            raise ValueError("public source object size differs")
        sizes.append(int(values[2]))
    if sum(sizes) > 268435456:
        raise ValueError("public source byte inventory exceeds bounds")
    stream = io.BytesIO(
        git_read(["cat-file", "--batch"], source_root, ("\n".join(ids) + "\n").encode())
    )
    bodies = {}
    for expected in ids:
        header = stream.readline().decode().strip().split()
        if (
            len(header) != 3
            or header[:2] != [expected, "blob"]
            or not header[2].isdigit()
            or int(header[2]) > 67108864
        ):
            raise ValueError("public source object frame differs")
        body = stream.read(int(header[2]))
        if (
            stream.read(1) != b"\n"
            or hashlib.sha1(b"blob " + header[2].encode() + b"\0" + body).hexdigest()
            != expected
        ):
            raise ValueError("public source object bytes differ")
        bodies[expected] = body
    if stream.read(1):
        raise ValueError("public source object stream has extra data")
    if entries.get("pyproject.toml", ("", ""))[0] not in {"100644", "100755"}:
        raise ValueError("public source metadata is missing")
    project = tomllib.loads(bodies[entries["pyproject.toml"][1]].decode())
    config = project["tool"]["hatch"]["build"]["targets"]["wheel"]
    if (
        config.get("packages") != ["src/scitex_writer"]
        or config.get("force-include") != {"scripts": "scitex_writer/scripts"}
        or config.get("exclude") != ["/src/scitex_writer/_django/frontend/node_modules"]
    ):
        raise ValueError("reviewed Writer package mapping changed")
    expected = {}
    source_paths = set()
    for path, (mode, oid) in entries.items():
        if path.startswith("src/scitex_writer/_django/frontend/node_modules/"):
            continue
        if path.startswith("src/scitex_writer/"):
            destination = path.removeprefix("src/")
        elif path.startswith("scripts/"):
            destination = "scitex_writer/" + path
        else:
            continue
        if mode not in {"100644", "100755"} or destination in expected:
            raise ValueError("unsupported or colliding public package member")
        expected[destination] = bodies[oid]
        source_paths.add(path)
    if not expected:
        raise ValueError("public source package membership is empty")
    with zipfile.ZipFile(io.BytesIO(wheel_raw)) as wheel:
        actual = {
            name
            for name in wheel.namelist()
            if name.startswith("scitex_writer/") and not name.endswith("/")
        }
        if actual != set(expected):
            raise ValueError("whole wheel public source membership differs")
        for name, body in expected.items():
            if wheel.read(name) != body:
                raise ValueError("wheel public source bytes differ")
        owners = {
            name.split("/", 1)[0] for name in wheel.namelist() if ".dist-info/" in name
        }
        if len(owners) != 1 or any(
            not name.startswith("scitex_writer/")
            and name.split("/", 1)[0] not in owners
            for name in wheel.namelist()
        ):
            raise ValueError("wheel contains undeclared payload")
    with tarfile.open(fileobj=io.BytesIO(sdist_raw), mode="r:gz") as sdist:
        members = sdist.getmembers()
        root = PurePosixPath(members[0].name).parts[0]
        actual = set()
        for item in members:
            if item.isdir():
                continue
            relative = item.name.removeprefix(root + "/")
            if relative == "PKG-INFO":
                continue
            if (
                relative not in entries
                or entries[relative][0] not in {"100644", "100755"}
                or not item.isfile()
            ):
                raise ValueError("sdist contains undeclared public payload")
            if sdist.extractfile(item).read() != bodies[entries[relative][1]]:
                raise ValueError("sdist public source bytes differ")
            actual.add(relative)
        if not (
            source_paths | {"README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml"}
        ).issubset(actual):
            raise ValueError("sdist public source membership is incomplete")
    manifest = [
        {"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        for name, body in sorted(expected.items())
    ]
    return {
        "git_commit": commit,
        "wheel_public_members": len(manifest),
        "source_membership_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "sdist_public_members": len(actual),
    }


def artifact_proof(directory, tag, commit, run, attempt, source_root=Path(".")):
    if (
        not TAG.fullmatch(tag)
        or not SHA.fullmatch(commit)
        or not run.isdigit()
        or not attempt.isdigit()
    ):
        raise ValueError("release identity is malformed")
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("artifact directory is unsafe")
    files = sorted(path for path in directory.iterdir() if path.name != PROOF)
    if (
        len(files) != 2
        or sum(path.name.endswith(".whl") for path in files) != 1
        or sum(path.name.endswith(".tar.gz") for path in files) != 1
    ):
        raise ValueError("release requires exactly one wheel and one sdist")
    rows = []
    payloads = {}
    for path in files:
        if (
            not path.name.startswith("scitex_writer-" + tag[1:] + "-")
            and path.name != "scitex_writer-" + tag[1:] + ".tar.gz"
        ):
            raise ValueError("artifact filename version differs")
        raw = regular_bytes(path)
        payloads["wheel" if path.name.endswith(".whl") else "sdist"] = raw
        identity = (
            wheel_identity(raw, tag[1:])
            if path.name.endswith(".whl")
            else sdist_identity(raw, tag[1:])
        )
        rows.append(
            {
                "name": path.name,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                **identity,
            }
        )
    source_identity = source_payload_identity(
        payloads["wheel"], payloads["sdist"], commit, source_root
    )
    return {
        "schema": "scitex-writer-release/v1",
        "repository": REPOSITORY,
        "tag": tag,
        "commit": commit,
        "run": run,
        "attempt": attempt,
        "files": rows,
        "source_membership": source_identity,
    }


def main(query=api):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["resolve", "write-proof", "verify-proof"])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit")
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--revalidate", action="store_true")
    args = parser.parse_args()
    if args.mode == "resolve":
        member_admission(query)
        identity = resolve(args.tag, query)
        if (
            os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_SHA") != identity["commit"]
        ):
            raise ValueError("push event and tag commit differ")
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            for key, value in identity.items():
                stream.write(key + "=" + value + "\n")
        print(json.dumps(identity))
        return
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if actual != args.commit:
        raise ValueError("checkout and release commit differ")
    proof = artifact_proof(
        args.dist,
        args.tag,
        args.commit or "",
        os.environ.get("GITHUB_RUN_ID", ""),
        os.environ.get("GITHUB_RUN_ATTEMPT", ""),
    )
    path = args.dist / PROOF
    if args.mode == "write-proof":
        with os.fdopen(
            os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
        ) as stream:
            json.dump(proof, stream, indent=2)
    elif json.loads(regular_bytes(path)) != proof:
        raise ValueError("artifact proof or byte identity differs")
    if args.revalidate:
        member_admission(query)
        if resolve(args.tag, query) != {
            "tag": args.tag,
            "commit": args.commit,
            "version": args.tag[1:],
        }:
            raise ValueError("release tag identity changed")
    print(json.dumps(proof))


if __name__ == "__main__":
    main()

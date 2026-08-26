#!/usr/bin/env python3
"""Fail-closed secret scan over every commit reachable from published Git refs.

The scanner never emits matched secret bytes. Findings contain only detector
metadata, paths, object ids, commit ids, and SHA-256 fingerprints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCHEMA = "nexus.git_history_secret_scan.v1"

PROVIDER_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("google_api_key", re.compile(rb"AIza[0-9A-Za-z_-]{35}")),
    ("aws_access_key", re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    (
        "github_token",
        re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    ),
    (
        "openai_api_key",
        re.compile(rb"(?:sk-proj-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,})"),
    ),
    ("slack_token", re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("stripe_live_key", re.compile(rb"(?:sk|rk)_live_[A-Za-z0-9]{16,}")),
)

PEM_PATTERN = re.compile(
    rb"-----BEGIN (?P<label>(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY)-----"
    rb"(?P<body>.*?)"
    rb"-----END (?P=label)-----",
    re.DOTALL,
)

ASSIGNMENT_PATTERN = re.compile(
    rb"(?im)^[ \t]*(?:export[ \t]+)?"
    rb"(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    rb"password|secret[_-]?key|private[_-]?key)"
    rb"[ \t]*[:=][ \t]*"
    rb"(?:\"(?P<double>[A-Za-z0-9_./+\-=]{20,})\"|"
    rb"'(?P<single>[A-Za-z0-9_./+\-=]{20,})'|"
    rb"(?P<bare>[A-Za-z0-9_./+\-=]{20,}))"
    rb"[ \t]*(?:#.*)?$"
)

SECRET_PATH_RE = re.compile(
    r"(?i)(?:^|/)(?:\.env(?:$|\.)|[^/]*\.(?:key|pem|p12|pfx|jks|keystore)$|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)$|credentials?(?:\.(?:json|ya?ml|toml))?$)"
)

PLACEHOLDER_WORDS = (
    b"example",
    b"placeholder",
    b"your_",
    b"your-",
    b"dummy",
    b"fake",
    b"must-not-pass",
    b"changeme",
    b"redacted",
    b"unconfigured",
)


@dataclass(frozen=True)
class Finding:
    detector: str
    subject_type: str
    fingerprint: str
    blocking: bool
    path: str | None = None
    object_id: str | None = None
    commit_id: str | None = None
    classification: str = "UNCLASSIFIED_SECRET"

    def as_dict(self) -> dict[str, object]:
        return {
            "detector": self.detector,
            "subject_type": self.subject_type,
            "fingerprint": self.fingerprint,
            "blocking": self.blocking,
            "classification": self.classification,
            "path": self.path,
            "object_id": self.object_id,
            "commit_id": self.commit_id,
        }


class ScanError(RuntimeError):
    pass


def _run(repo: Path, *args: str, input_text: str | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ScanError(f"git {' '.join(args[:2])} failed with exit {proc.returncode}")
    return proc.stdout


def _fingerprint(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _entropy(value: bytes) -> float:
    if not value:
        return 0.0
    counts: dict[int, int] = {}
    for item in value:
        counts[item] = counts.get(item, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _is_repeated_sequence_prefix(value: bytes, sequence: bytes) -> bool:
    if len(value) < 20:
        return False
    repeated = (sequence * ((len(value) // len(sequence)) + 1))[: len(value)]
    return value == repeated


def _has_delimited_placeholder_marker(value: bytes) -> bool:
    separators = b"-_./"
    for configured_marker in PLACEHOLDER_WORDS:
        marker = configured_marker.strip(b"-_")
        offset = 0
        while True:
            index = value.find(marker, offset)
            if index < 0:
                break
            end = index + len(marker)
            left_boundary = index == 0 or value[index - 1] in separators
            right_boundary = end == len(value) or value[end] in separators
            if left_boundary and right_boundary:
                return True
            offset = index + 1
    return False


def _looks_placeholder(value: bytes) -> bool:
    normalized = value.lower().strip(b" \t\r\n\"'")
    for prefix in (b"sk-proj-", b"sk-", b"ghp_", b"github_pat_", b"aiza"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    if _has_delimited_placeholder_marker(normalized):
        return True
    if _is_repeated_sequence_prefix(normalized, b"1234567890"):
        return True
    alphabet = b"abcdefghijklmnopqrstuvwxyz"
    if normalized.startswith(alphabet):
        tail = normalized[len(alphabet) :]
        if not tail:
            return True
        if len(tail) >= 6 and any(
            template.startswith(tail)
            for template in (b"1234567890", b"0123456789", b"abcdef1234567890")
        ):
            return True
    synthetic_atoms = (
        b"0123456789abcdef",
        b"1234567890abcdef",
        b"abcdefghijklmnopqrstuvwxyz",
        b"abcdefghijklmnopqrstuvwxyz0123456789abcdef",
    )
    for atom in synthetic_atoms:
        if len(normalized) >= 16 and normalized in (atom * 4):
            return True
    if normalized.startswith(b"real1234567890abcdef"):
        return True
    if not value.strip(b"0") or not value.strip(b"xX"):
        return True
    if len(value) >= 32 and len(value) % 2 == 0:
        half = len(value) // 2
        if value[:half] == value[half:]:
            return True
    alphabet_and_digits = b"abcdefghijklmnopqrstuvwxyz0123456789"
    if len(value) >= 20 and value.lower().strip(b"-_./+") in alphabet_and_digits:
        return True
    return False


def _published_refs(repo: Path) -> list[tuple[str, str]]:
    text = _run(
        repo,
        "for-each-ref",
        "--format=%(refname) %(objectname)",
        "refs/remotes/origin",
        "refs/tags",
    )
    refs: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        name, oid = line.split(" ", 1)
        if name == "refs/remotes/origin/HEAD":
            continue
        if not re.fullmatch(r"[0-9a-f]{40,64}", oid):
            raise ScanError(f"invalid ref object id for {name}")
        refs.append((name, oid))
    if not refs:
        raise ScanError("no published branch/tag refs available")
    return sorted(refs)


def _reachable_commits(repo: Path, refs: Iterable[tuple[str, str]]) -> list[str]:
    tips = "".join(f"{oid}\n" for _, oid in refs)
    commits = [
        line for line in _run(repo, "rev-list", "--stdin", input_text=tips).splitlines() if line
    ]
    if not commits:
        raise ScanError("published refs produced no reachable commits")
    if any(not re.fullmatch(r"[0-9a-f]{40,64}", commit) for commit in commits):
        raise ScanError("rev-list returned malformed commit id")
    return sorted(set(commits))


def _historical_blob_paths(repo: Path, refs: Iterable[tuple[str, str]]) -> dict[str, set[str]]:
    tips = "".join(f"{oid}\n" for _, oid in refs).encode("ascii")
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "log",
            "--format=",
            "--raw",
            "--root",
            "-m",
            "-r",
            "--no-renames",
            "--no-abbrev",
            "-z",
            "--stdin",
        ],
        input=tips,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ScanError(f"git log historical paths failed with exit {proc.returncode}")

    fields = [field for field in proc.stdout.split(b"\x00") if field]
    if len(fields) % 2:
        raise ScanError("git log historical path stream is malformed")

    object_paths: dict[str, set[str]] = {}
    for index in range(0, len(fields), 2):
        header = fields[index].lstrip(b"\n")
        path_bytes = fields[index + 1]
        parts = header.split()
        if len(parts) != 5 or not parts[0].startswith(b":"):
            raise ScanError("git log historical path record is malformed")
        new_mode = parts[1]
        new_oid_bytes = parts[3]
        status = parts[4]
        if status.startswith(b"D") or not new_oid_bytes.strip(b"0"):
            continue
        if new_mode == b"160000":
            continue
        if new_mode not in {b"100644", b"100755", b"120000"}:
            raise ScanError("git log historical path record has an unsupported object mode")
        try:
            new_oid = new_oid_bytes.decode("ascii", "strict")
        except UnicodeDecodeError as exc:
            raise ScanError("git log historical path object id is non-ASCII") from exc
        if not re.fullmatch(r"[0-9a-f]{40,64}", new_oid):
            raise ScanError("git log historical path object id is malformed")
        path = path_bytes.decode("utf-8", "surrogateescape")
        if not path:
            raise ScanError("git log historical path is empty")
        object_paths.setdefault(new_oid, set()).add(path)
    return object_paths


def _reachable_blob_paths(
    repo: Path, refs: Iterable[tuple[str, str]]
) -> tuple[dict[str, set[str]], int]:
    refs = list(refs)
    tips = "".join(f"{oid}\n" for _, oid in refs)
    lines = _run(repo, "rev-list", "--objects", "--stdin", input_text=tips).splitlines()
    object_ids: list[str] = []
    for line in lines:
        if not line:
            continue
        oid = line.partition(" ")[0]
        if not re.fullmatch(r"[0-9a-f]{40,64}", oid):
            raise ScanError("rev-list --objects returned malformed object id")
        object_ids.append(oid)

    reachable_objects = set(object_ids)
    historical_paths = _historical_blob_paths(repo, refs)
    if any(oid not in reachable_objects for oid in historical_paths):
        raise ScanError("historical path references an object outside the reachable object set")

    check = _run(
        repo,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_text="".join(f"{oid}\n" for oid in sorted(reachable_objects)),
    )
    blobs: dict[str, set[str]] = {}
    for line in check.splitlines():
        parts = line.split(" ")
        if len(parts) != 3:
            raise ScanError("cat-file batch-check returned malformed record")
        oid, obj_type, size_text = parts
        if obj_type == "blob":
            try:
                size = int(size_text)
            except ValueError as exc:
                raise ScanError("cat-file returned invalid object size") from exc
            if size > 32 * 1024 * 1024:
                raise ScanError(f"blob {oid} exceeds 32 MiB scan ceiling")
            blobs[oid] = historical_paths.get(oid, set())
    return blobs, len(reachable_objects)


def _commit_messages(repo: Path, refs: Iterable[tuple[str, str]]) -> Iterable[tuple[str, bytes]]:
    tips = "".join(f"{oid}\n" for _, oid in refs)
    raw = _run(
        repo,
        "log",
        "--format=%H%x00%B%x00",
        "--stdin",
        input_text=tips,
    ).encode("utf-8", "surrogateescape")
    fields = raw.split(b"\x00")
    if fields and fields[-1] in (b"", b"\n"):
        fields.pop()
    if len(fields) % 2:
        raise ScanError("git log returned malformed commit-message stream")
    for index in range(0, len(fields), 2):
        commit = fields[index].strip().decode("ascii", "strict")
        message = fields[index + 1]
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise ScanError("git log returned malformed commit id")
        yield commit, message


def _blob_stream(repo: Path, object_ids: Iterable[str]) -> Iterable[tuple[str, bytes]]:
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.stdin is None or proc.stdout is None or proc.stderr is None:
        proc.kill()
        raise ScanError("git cat-file batch pipes unavailable")
    try:
        for expected_oid in object_ids:
            proc.stdin.write(expected_oid.encode("ascii") + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline().decode("ascii", "strict").strip()
            parts = header.split(" ")
            if len(parts) != 3:
                raise ScanError("git cat-file batch returned malformed header")
            oid, obj_type, size_text = parts
            if oid != expected_oid or obj_type != "blob":
                raise ScanError("git cat-file batch object identity mismatch")
            try:
                size = int(size_text)
            except ValueError as exc:
                raise ScanError("git cat-file batch returned invalid size") from exc
            data = proc.stdout.read(size)
            separator = proc.stdout.read(1)
            if len(data) != size or separator != b"\n":
                raise ScanError("git cat-file batch returned truncated blob")
            yield oid, data
        proc.stdin.close()
        return_code = proc.wait(timeout=30)
        if return_code != 0:
            raise ScanError(f"git cat-file batch failed with exit {return_code}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def _scan_bytes(
    data: bytes,
    *,
    subject_type: str,
    object_id: str | None = None,
    commit_id: str | None = None,
    path: str | None = None,
) -> list[Finding]:
    findings: list[Finding] = []

    for match in PEM_PATTERN.finditer(data):
        body = re.sub(rb"\s+", b"", match.group("body"))
        if len(body) < 64 or _looks_placeholder(body):
            continue
        findings.append(
            Finding(
                detector="pem_private_key",
                subject_type=subject_type,
                fingerprint=_fingerprint(match.group(0)),
                blocking=True,
                path=path,
                object_id=object_id,
                commit_id=commit_id,
            )
        )

    provider_spans: list[tuple[int, int]] = []
    for detector, pattern in PROVIDER_PATTERNS:
        for match in pattern.finditer(data):
            provider_spans.append(match.span())
            placeholder = _looks_placeholder(match.group(0))
            findings.append(
                Finding(
                    detector=detector,
                    subject_type=subject_type,
                    fingerprint=_fingerprint(match.group(0)),
                    blocking=not placeholder,
                    classification=("OBVIOUS_FIXTURE" if placeholder else "UNCLASSIFIED_SECRET"),
                    path=path,
                    object_id=object_id,
                    commit_id=commit_id,
                )
            )

    for match in ASSIGNMENT_PATTERN.finditer(data):
        value_group = next(
            (name for name in ("double", "single", "bare") if match.group(name) is not None),
            None,
        )
        if value_group is None:
            raise ScanError("secret-assignment detector returned no value")
        value = match.group(value_group)
        value_start, value_end = match.span(value_group)
        if any(start <= value_start and value_end <= end for start, end in provider_spans):
            continue
        placeholder = _looks_placeholder(value)
        if placeholder or _entropy(value) < 3.5:
            continue
        findings.append(
            Finding(
                detector="high_entropy_secret_assignment",
                subject_type=subject_type,
                fingerprint=_fingerprint(value),
                blocking=True,
                path=path,
                object_id=object_id,
                commit_id=commit_id,
            )
        )
    return findings


def scan_repository(repo: Path) -> dict[str, object]:
    repo = repo.resolve()
    if not (repo / ".git").exists() and not _run(repo, "rev-parse", "--git-dir").strip():
        raise ScanError("repository git directory unavailable")

    refs = _published_refs(repo)
    commits = _reachable_commits(repo, refs)
    blobs, object_count = _reachable_blob_paths(repo, refs)
    findings: list[Finding] = []

    scanned_messages = 0
    for commit, message in _commit_messages(repo, refs):
        findings.extend(_scan_bytes(message, subject_type="commit_message", commit_id=commit))
        scanned_messages += 1
    if scanned_messages != len(commits):
        raise ScanError("commit-message scan count does not match reachable commit count")

    for oid, data in _blob_stream(repo, sorted(blobs)):
        paths = blobs[oid]
        scan_paths = sorted(paths) or [None]
        content_findings = _scan_bytes(data, subject_type="blob", object_id=oid)
        for item in content_findings:
            for path in scan_paths:
                findings.append(
                    Finding(
                        detector=item.detector,
                        subject_type=item.subject_type,
                        fingerprint=item.fingerprint,
                        blocking=item.blocking,
                        classification=item.classification,
                        path=path,
                        object_id=oid,
                    )
                )
        for path in sorted(paths):
            if not SECRET_PATH_RE.search(path):
                continue
            if path.lower().endswith((".template", ".example", ".sample")):
                continue
            if data.strip():
                findings.append(
                    Finding(
                        detector="secret_bearing_path",
                        subject_type="blob_path",
                        fingerprint=_fingerprint((oid + "\0" + path).encode()),
                        blocking=True,
                        path=path,
                        object_id=oid,
                    )
                )

    deduped: dict[tuple[object, ...], Finding] = {}
    for item in findings:
        key = (
            item.detector,
            item.subject_type,
            item.fingerprint,
            item.path,
            item.object_id,
            item.commit_id,
        )
        deduped[key] = item
    ordered = sorted(
        deduped.values(),
        key=lambda item: (
            item.blocking is False,
            item.detector,
            item.path or "",
            item.commit_id or "",
            item.object_id or "",
        ),
    )
    blocking = [item for item in ordered if item.blocking]
    return {
        "schema": SCHEMA,
        "status": "FAIL" if blocking else "PASS",
        "blocking": bool(blocking),
        "published_ref_count": len(refs),
        "branch_ref_count": sum(name.startswith("refs/remotes/origin/") for name, _ in refs),
        "tag_ref_count": sum(name.startswith("refs/tags/") for name, _ in refs),
        "reachable_commit_count": len(commits),
        "reachable_object_count": object_count,
        "reachable_blob_count": len(blobs),
        "finding_count": len(ordered),
        "blocking_finding_count": len(blocking),
        "findings": [item.as_dict() for item in ordered],
        "secret_values_emitted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        receipt = scan_repository(Path(args.repo))
        exit_code = 1 if receipt["blocking"] else 0
    except Exception as exc:
        receipt = {
            "schema": SCHEMA,
            "status": "ERROR",
            "blocking": True,
            "error_class": type(exc).__name__,
            "error_fingerprint": hashlib.sha256(str(exc).encode()).hexdigest(),
            "secret_values_emitted": False,
        }
        exit_code = 2
    payload = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

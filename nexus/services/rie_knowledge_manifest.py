"""Owner-declared repository knowledge manifest + producer wiring (#1579).

The manifest (``docs/knowledge/rie_knowledge_manifest.v1.json``) declares which
repo-owned documents are intended model context and which source files each
names. It is declarative, never derived. This module:

* loads and schema-validates it (fail closed on a malformed manifest);
* recomputes declared source hashes and reports ``STALE_DECLARATION`` per entry
  (it never fails hard on staleness);
* builds ``changes[]`` / ``observed_source_sha256`` from git and calls the
  existing ``build_codeintel_knowledge_evidence``.

No network, no model call, no RIE import (the engine is only reached through
``rie_knowledge_applicability``'s subprocess adapter). No Planner capability,
route or policy authority is added.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from nexus.services import rie_knowledge_applicability as ka

MANIFEST_SCHEMA = "nexus.rie_knowledge_manifest.v1"
MANIFEST_CLAIM_CEILING = "REPOSITORY_KNOWLEDGE_MANIFEST_DECLARATION_ONLY"
DEFAULT_MANIFEST_PATH = "docs/knowledge/rie_knowledge_manifest.v1.json"
STALE_DECLARATION = "STALE_DECLARATION"
CURRENT_DECLARATION = "CURRENT_DECLARATION"

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_TOP_KEYS = {"schema", "revision", "claim_ceiling", "notes", "entries"}
_ENTRY_KEYS = {"id", "path", "source_refs", "covers", "in_scope"}
_GIT_TIMEOUT_SECONDS = 60

Reader = Callable[[str], "bytes | None"]


class RieKnowledgeManifestError(ValueError):
    """Fail-closed manifest/producer error with a stable machine code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relpath(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    p = PurePosixPath(value)
    return not p.is_absolute() and ".." not in p.parts and str(p) == value


# --------------------------------------------------------------------------- #
# load + validate
# --------------------------------------------------------------------------- #
def validate_manifest(manifest: Any) -> dict[str, Any]:
    """Schema-check a manifest mapping; return it (as a dict) or raise."""
    if not isinstance(manifest, Mapping):
        raise RieKnowledgeManifestError("MANIFEST_NOT_OBJECT")
    if set(manifest) != _TOP_KEYS:
        raise RieKnowledgeManifestError(
            "MANIFEST_KEYS_INVALID", ",".join(sorted(set(manifest) ^ _TOP_KEYS))
        )
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise RieKnowledgeManifestError("MANIFEST_SCHEMA_MISMATCH")
    if manifest["claim_ceiling"] != MANIFEST_CLAIM_CEILING:
        raise RieKnowledgeManifestError("MANIFEST_CLAIM_CEILING_MISMATCH")
    if not isinstance(manifest["revision"], str) or not _SHA40.fullmatch(manifest["revision"]):
        raise RieKnowledgeManifestError("MANIFEST_REVISION_INVALID")
    if not isinstance(manifest["notes"], str) or not manifest["notes"].strip():
        raise RieKnowledgeManifestError("MANIFEST_NOTES_MISSING")
    entries = manifest["entries"]
    if not isinstance(entries, list) or not entries:
        raise RieKnowledgeManifestError("MANIFEST_ENTRIES_INVALID")
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        tag = f"entry[{index}]"
        if not isinstance(entry, Mapping) or set(entry) != _ENTRY_KEYS:
            raise RieKnowledgeManifestError("ENTRY_KEYS_INVALID", tag)
        entry_id = entry["id"]
        if not isinstance(entry_id, str) or not entry_id or entry_id in seen:
            raise RieKnowledgeManifestError("ENTRY_ID_INVALID_OR_DUPLICATE", tag)
        seen.add(entry_id)
        if not _safe_relpath(entry["path"]):
            raise RieKnowledgeManifestError("ENTRY_PATH_INVALID", entry_id)
        if entry["in_scope"] is not True:
            raise RieKnowledgeManifestError("ENTRY_IN_SCOPE_NOT_TRUE", entry_id)
        refs = entry["source_refs"]
        if not isinstance(refs, list) or not refs:
            raise RieKnowledgeManifestError("ENTRY_SOURCE_REFS_INVALID", entry_id)
        for ref in refs:
            if (
                not isinstance(ref, Mapping)
                or set(ref) != {"path", "expected_content_sha256"}
                or not _safe_relpath(ref["path"])
                or not isinstance(ref["expected_content_sha256"], str)
                or not _SHA64.fullmatch(ref["expected_content_sha256"])
            ):
                raise RieKnowledgeManifestError("ENTRY_SOURCE_REF_INVALID", entry_id)
        covers = entry["covers"]
        if not isinstance(covers, list) or not all(
            isinstance(c, str) and c.strip("*/") for c in covers
        ):
            raise RieKnowledgeManifestError("ENTRY_COVERS_INVALID_OR_TOO_BROAD", entry_id)
    return dict(manifest)


def load_manifest(path: Path | str) -> dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise RieKnowledgeManifestError("MANIFEST_UNREADABLE", type(exc).__name__) from exc
    return validate_manifest(data)


# --------------------------------------------------------------------------- #
# readers + declaration evaluation
# --------------------------------------------------------------------------- #
def worktree_reader(repo_root: Path | str) -> Reader:
    root = Path(repo_root)

    def read(path: str) -> bytes | None:
        try:
            return (root / path).read_bytes()
        except OSError:
            return None

    return read


def git_blob_reader(repo_root: Path | str, revision: str) -> Reader:
    root = str(repo_root)

    def read(path: str) -> bytes | None:
        try:
            proc = subprocess.run(
                ["git", "-C", root, "show", f"{revision}:{path}"],
                capture_output=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return proc.stdout if proc.returncode == 0 else None

    return read


def evaluate_manifest(manifest: Mapping[str, Any], reader: Reader) -> list[dict[str, Any]]:
    """Recompute declared hashes. Stale entries are reported, never raised."""
    result: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        stale: list[dict[str, str]] = []
        for ref in entry["source_refs"]:
            data = reader(ref["path"])
            if data is None:
                stale.append({"path": ref["path"], "reason": "SOURCE_MISSING"})
            elif sha256_bytes(data) != ref["expected_content_sha256"]:
                stale.append({"path": ref["path"], "reason": "SOURCE_SHA_MISMATCH"})
        artifact_exists = reader(entry["path"]) is not None
        result.append({
            "id": entry["id"],
            "path": entry["path"],
            "artifact_exists": artifact_exists,
            "declaration_status": (
                STALE_DECLARATION if stale or not artifact_exists else CURRENT_DECLARATION
            ),
            "stale_sources": stale,
            "artifact_missing": not artifact_exists,
        })
    return result


# --------------------------------------------------------------------------- #
# git change collection
# --------------------------------------------------------------------------- #
def parse_name_status(text: str) -> list[dict[str, str]]:
    """Parse tab-separated ``git diff --name-status`` output into RIE changes."""
    return _changes_from_records([line.split("\t") for line in text.splitlines() if line.strip()])


def parse_name_status_z(data: bytes) -> list[dict[str, str]]:
    """Parse ``git diff --name-status -z`` output (exact for unusual paths)."""
    parts = [p.decode("utf-8", "surrogateescape") for p in data.split(b"\x00")]
    records: list[list[str]] = []
    i = 0
    while i < len(parts) and parts[i]:
        code = parts[i]
        width = 3 if code[:1] in {"R", "C"} else 2
        records.append(parts[i : i + width])
        i += width
    return _changes_from_records(records)


def _changes_from_records(records: Sequence[Sequence[str]]) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for rec in records:
        code = rec[0][:1]
        if code in {"R", "C"} and len(rec) == 3:
            if code == "R":
                changes.append({"kind": "RENAME", "path": rec[2], "old_path": rec[1]})
            else:
                changes.append({"kind": "ADD", "path": rec[2]})
        elif code == "A" and len(rec) == 2:
            changes.append({"kind": "ADD", "path": rec[1]})
        elif code in {"M", "T"} and len(rec) == 2:
            changes.append({"kind": "MODIFY", "path": rec[1]})
        elif code == "D" and len(rec) == 2:
            changes.append({"kind": "DELETE", "path": "", "old_path": rec[1]})
        else:
            raise RieKnowledgeManifestError("CHANGE_RECORD_UNSUPPORTED", rec[0][:8])
    return changes


def git_changes(repo_root: Path | str, base_sha: str, head_sha: str) -> list[dict[str, str]]:
    """Run ``git diff --name-status -z -M base..head`` (read-only)."""
    for sha in (base_sha, head_sha):
        if not _SHA40.fullmatch(sha):
            raise RieKnowledgeManifestError("CHANGE_SHA_INVALID")
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "diff",
                "--name-status",
                "-z",
                "-M",
                f"{base_sha}..{head_sha}",
            ],
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RieKnowledgeManifestError("GIT_DIFF_FAILED", type(exc).__name__) from exc
    if proc.returncode != 0:
        raise RieKnowledgeManifestError("GIT_DIFF_FAILED")
    return parse_name_status_z(proc.stdout)


# --------------------------------------------------------------------------- #
# producer wiring
# --------------------------------------------------------------------------- #
def build_manifest_knowledge_evidence(
    *,
    manifest: Mapping[str, Any],
    identity: Mapping[str, Any],
    changes: Sequence[Mapping[str, Any]],
    reader: Reader,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Build RIE inputs from manifest + git evidence; call the existing adapter.

    ``reader`` must read blobs at the identity ``head_sha`` (``git_blob_reader``).
    Returns ``{"evidence": {"knowledge_applicability": ...}, "manifest": {...}}``.
    Stale declarations are appended to the projection's ``evidence_gaps``.
    """
    manifest = validate_manifest(manifest)
    declarations = evaluate_manifest(manifest, reader)
    live = {d["id"] for d in declarations if d["artifact_exists"]}
    artifacts: list[dict[str, Any]] = []
    observed: dict[str, str] = {}
    scope: set[str] = set()
    for entry in manifest["entries"]:
        if entry["id"] not in live:
            continue
        artifacts.append({
            "artifact_id": entry["id"],
            "path": entry["path"],
            "source_refs": [
                {"source_path": r["path"], "expected_content_sha256": r["expected_content_sha256"]}
                for r in entry["source_refs"]
            ],
            "covers": list(entry["covers"]),
        })
        scope.update(entry["covers"])
        for ref in entry["source_refs"]:
            scope.add(ref["path"])
            data = reader(ref["path"])
            if data is not None:
                observed[ref["path"]] = sha256_bytes(data)
    evidence = ka.build_codeintel_knowledge_evidence(
        snapshot=identity,
        knowledge_artifacts=artifacts,
        changes=changes,
        observed_source_sha256=observed,
        in_scope=sorted(scope),
        collection_complete=True,
        env=env,
        runner=runner,
    )
    gaps = [
        f"MANIFEST_{STALE_DECLARATION}:{d['id']}"
        + (":ARTIFACT_MISSING" if d["artifact_missing"] else "")
        for d in declarations
        if d["declaration_status"] == STALE_DECLARATION
    ]
    projection = evidence["knowledge_applicability"]
    if gaps:
        projection["evidence_gaps"] = [
            ka._bound(g, ka.MAX_GAP_CHARS)
            for g in [*projection["evidence_gaps"], *gaps][: ka.MAX_GAPS]
        ]
    return {
        "evidence": evidence,
        "manifest": {
            "schema": manifest["schema"],
            "revision": manifest["revision"],
            "claim_ceiling": MANIFEST_CLAIM_CEILING,
            "declarations": declarations,
        },
    }

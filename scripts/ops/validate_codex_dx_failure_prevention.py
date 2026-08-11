"""Fail-closed validation for the bounded Codex DX prevention registry."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping


class PreventionRegistryError(ValueError):
    """The registry is malformed or claims an unsupported prevention."""


FAILURE_CLASSES = {
    "setup",
    "fixture",
    "command",
    "environment",
    "secret",
    "convention",
    "context",
}
ENTRY_KEYS = {
    "id",
    "failure_class",
    "summary",
    "evidence_refs",
    "prevention_seam",
    "owner",
    "status",
    "removal_condition",
}
SEAM_KEYS = {"id", "kind", "path", "anchor"}
TOP_KEYS = {"schema_version", "authority", "known_classes", "unassessed_classes", "entries"}
KINDS = {"test", "fixture", "command", "instruction"}
_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_ONE_LINE = re.compile(r"^[^\r\n]+$")
BEFORE_RECEIPT_SHA256 = "f9c6268b3d5eaf7e453159656901813b05ba6cf87abbf42e106b193a45a90657"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreventionRegistryError(message)


def _text(value: Any, label: str, *, min_length: int = 1, max_length: int = 240) -> str:
    _require(isinstance(value, str), f"{label} must be a string")
    _require(
        min_length <= len(value) <= max_length and _ONE_LINE.fullmatch(value) is not None,
        f"{label} must be bounded and one line",
    )
    return value


def _safe_relative_path(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise PreventionRegistryError("prevention path escapes registry root") from exc
    _require(path.is_file(), f"prevention path does not exist: {value}")
    return path


def validate_registry(payload: Mapping[str, Any], *, root: Path | None = None) -> int:
    """Validate and return the number of admitted prevention entries."""
    root = (root or Path(__file__).resolve().parents[2]).resolve()
    _require(isinstance(payload, Mapping) and set(payload) == TOP_KEYS, "registry keys are invalid")
    _require(
        len(json.dumps(payload, ensure_ascii=False).encode()) <= 64 * 1024, "registry exceeds 64KiB"
    )
    _require(
        payload.get("schema_version") == "codex-dx-failure-prevention-v1",
        "unsupported schema version",
    )
    _require(
        payload.get("authority") == "navigation_and_evidence_only", "registry authority is invalid"
    )
    known = payload.get("known_classes")
    unassessed = payload.get("unassessed_classes")
    _require(known == sorted(FAILURE_CLASSES), "known failure classes are invalid")
    _require(unassessed == ["secret"], "unassessed classes must identify the secret coverage gap")
    entries = payload.get("entries")
    _require(
        isinstance(entries, list) and 0 < len(entries) <= 7, "entries are required and bounded"
    )

    ids: set[str] = set()
    classes: set[str] = set()
    seams: set[str] = set()
    resolved_seams: set[tuple[Path, str]] = set()
    semantic: set[str] = set()
    evidence_seen: set[str] = set()
    for entry in entries:
        _require(isinstance(entry, Mapping) and set(entry) == ENTRY_KEYS, "entry keys are invalid")
        entry_id = _text(entry.get("id"), "entry id", max_length=64)
        _require(_ID.fullmatch(entry_id) is not None, "entry id format is invalid")
        _require(entry_id not in ids, "duplicate entry id")
        ids.add(entry_id)
        failure_class = _text(entry.get("failure_class"), "failure class", max_length=40)
        _require(failure_class in FAILURE_CLASSES, f"unsupported failure class: {failure_class}")
        _require(
            failure_class != "secret", "secret is an unassessed coverage gap, not an admitted class"
        )
        _require(failure_class not in classes, "duplicate failure class")
        classes.add(failure_class)
        summary = _text(entry.get("summary"), "summary", max_length=240)
        semantic_key = re.sub(r"[^a-z0-9]+", " ", summary.lower()).strip()
        _require(semantic_key not in semantic, "semantic duplicate summary")
        semantic.add(semantic_key)
        refs = entry.get("evidence_refs")
        _require(
            isinstance(refs, list) and 0 < len(refs) <= 3,
            "evidence refs are required and bounded",
        )
        for ref in refs:
            ref = _text(ref, "evidence reference", max_length=240)
            _require(ref not in evidence_seen, "duplicate evidence reference")
            evidence_seen.add(ref)
            _require(ref.count("#") == 1, "evidence reference must be path#anchor")
            path_value, anchor = ref.split("#", 1)
            lexical_parts = Path(path_value).parts
            _require(
                path_value
                and anchor
                and not Path(path_value).is_absolute()
                and not path_value.startswith("./")
                and "//" not in path_value
                and "." not in lexical_parts
                and ".." not in lexical_parts,
                "evidence reference path or anchor is invalid or aliased",
            )
            evidence_path = _safe_relative_path(root, path_value)
            evidence_bytes = evidence_path.read_bytes()
            evidence_text = evidence_bytes.decode("utf-8", errors="ignore")
            if path_value == "configs/benchmarks/codex_dx_before_v1.json":
                _require(
                    hashlib.sha256(evidence_bytes).hexdigest() == BEFORE_RECEIPT_SHA256,
                    "before evidence receipt identity is invalid",
                )
                source = json.loads(evidence_text)
                evidence_ids = {item.get("id") for item in source.get("baseline_evidence", [])}
                evidence_ids.update(item.get("trial_id") for item in source.get("trials", []))
                _require(
                    anchor in evidence_ids,
                    "evidence anchor is not an exact structured ID",
                )
                _validate_evidence_semantics(failure_class, source, anchor)
            else:
                _require(anchor in evidence_text, "evidence anchor is not physically present")
        seam = entry.get("prevention_seam")
        _require(
            isinstance(seam, Mapping) and set(seam) == SEAM_KEYS,
            "prevention seam is narrative-only or malformed",
        )
        seam_id = _text(seam.get("id"), "seam id", max_length=64)
        _require(
            _ID.fullmatch(seam_id) is not None and seam_id not in seams, "duplicate prevention seam"
        )
        seams.add(seam_id)
        kind = _text(seam.get("kind"), "seam kind", max_length=20)
        _require(kind in KINDS, "unsupported prevention seam kind")
        path_value = _text(seam.get("path"), "prevention path", max_length=240)
        lexical_parts = Path(path_value).parts
        _require(
            not Path(path_value).is_absolute()
            and not path_value.startswith("./")
            and "//" not in path_value
            and "." not in lexical_parts
            and ".." not in lexical_parts,
            "prevention path must be relative without aliases",
        )
        seam_path = _safe_relative_path(root, path_value)
        anchor = _text(seam.get("anchor"), "prevention anchor", max_length=180)
        seam_text = seam_path.read_text(encoding="utf-8", errors="ignore")
        if kind in {"test", "command", "fixture"} and path_value.endswith(".py"):
            _require(
                re.search(
                    rf"^\s*(?:def|class)\s+{re.escape(anchor)}(?:\(|:)", seam_text, re.MULTILINE
                )
                is not None,
                "prevention anchor is not an exact Python identifier",
            )
        elif kind == "instruction":
            _require(
                anchor in seam_text.splitlines(), "prevention anchor is not an exact Markdown line"
            )
        else:
            _require(anchor in seam_text, "prevention anchor is not physically present")
        seam_key = (seam_path, anchor)
        _require(seam_key not in resolved_seams, "duplicate resolved prevention seam")
        resolved_seams.add(seam_key)
        owner = _text(entry.get("owner"), "owner", max_length=120)
        _require(owner != "unassigned", "prevention owner is required")
        _require(entry.get("status") in {"active", "retired"}, "invalid prevention status")
        _text(entry.get("removal_condition"), "removal condition", max_length=240)
    _require(
        classes == FAILURE_CLASSES - {"secret"},
        "registry must cover exactly six substantiated recurring classes",
    )
    before_path = root / "configs/benchmarks/codex_dx_before_v1.json"
    before = json.loads(before_path.read_text(encoding="utf-8"))
    _require(
        all(trial.get("secret_reads") == 0 for trial in before.get("trials", [])),
        "secret can remain unassessed only while the bounded history has no secret failure",
    )
    return len(entries)


def _validate_evidence_semantics(
    failure_class: str, source: Mapping[str, Any], anchor: str
) -> None:
    if failure_class == "command":
        _require(
            not anchor.startswith("before-"),
            "command evidence must bind a baseline failure",
        )
        item = next(item for item in source["baseline_evidence"] if item["id"] == anchor)
        _require(
            item["id"] == "missing-benchmark-runner" and "0/5" in item["result"],
            "command evidence is unsupported",
        )
        return

    _require(anchor.startswith("before-"), "trial evidence is required for this class")
    if anchor.startswith("before-"):
        trial = next(item for item in source["trials"] if item["trial_id"] == anchor)
        sessions = [
            session
            for session in source.get("session_artifacts", [])
            if session.get("session_id") == trial.get("session_id")
        ]
        _require(len(sessions) == 1, "trial session binding is invalid")
        session = sessions[0]
        artifact = trial.get("verifier_artifact", {})
        _require(
            artifact.get("ref") == f"inline-session:{session['session_id']}"
            and artifact.get("sha256") == session.get("sha256")
            and session.get("repetition") == trial.get("repetition")
            and session.get("source_commit") == trial.get("source_commit"),
            "trial session artifact identity is invalid",
        )
        if failure_class == "setup":
            _require(
                trial["task_id"] == "dx-setup-v1" and trial["outcome"] == "failure",
                "setup evidence is unsupported",
            )
        elif failure_class == "fixture":
            _require(
                trial["task_id"] == "dx-focused-test-v1" and trial["outcome"] == "infra_failure",
                "fixture evidence is unsupported",
            )
        elif failure_class == "environment":
            _require(
                trial["task_id"] == "dx-focused-test-v1" and trial["outcome"] == "infra_failure",
                "environment evidence is unsupported",
            )
            answers = [
                item.get("answer", "")
                for item in session.get("payload", {}).get("trials", [])
                if item.get("task_class") == "focused_test"
            ]
            _require(
                any("temporary" in a.lower() or "writable" in a.lower() for a in answers),
                "environment evidence lacks bound explanation",
            )
        elif failure_class == "convention":
            answers = [
                item.get("answer", "")
                for item in session.get("payload", {}).get("trials", [])
                if item.get("task_class") == "verification"
            ]
            _require(
                trial["task_id"] == "dx-verification-v1"
                and any("contradict" in a.lower() for a in answers),
                "convention evidence is unsupported",
            )
        elif failure_class == "context":
            _require(
                trial["task_id"] == "dx-orientation-v1"
                and trial.get("context", {}).get("bytes", 0) > 16000,
                "context evidence is unsupported",
            )


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 1:
        print("usage: validate_codex_dx_failure_prevention.py REGISTRY.json", file=sys.stderr)
        return 2
    registry_path = Path(args[0]).resolve()
    try:
        if registry_path.stat().st_size > 64 * 1024:
            raise PreventionRegistryError("registry file exceeds 64KiB")
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        count = validate_registry(payload, root=registry_path.parents[1])
    except (OSError, json.JSONDecodeError, PreventionRegistryError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {count} recurring failure classes mapped; 1 unassessed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

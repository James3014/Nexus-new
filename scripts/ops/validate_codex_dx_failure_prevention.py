"""Fail-closed validation for the repository-portable Codex DX registry."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping


class PreventionRegistryError(ValueError):
    """The registry is malformed or references unsupported evidence."""


FAILURE_CLASSES = {"setup", "fixture", "command", "environment", "secret", "convention", "context"}
TOP_KEYS = {"schema_version", "authority", "known_classes", "unassessed_classes", "entries"}
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
KINDS = {"test", "fixture", "command", "instruction"}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreventionRegistryError(message)


def _text(value: Any, label: str, *, max_length: int = 240) -> str:
    _require(isinstance(value, str), f"{label} must be a string")
    _require(
        0 < len(value) <= max_length and "\r" not in value and "\n" not in value,
        f"{label} must be bounded and one line",
    )
    return value


def _relative_file(root: Path, value: str, label: str) -> Path:
    _text(value, label)
    path = Path(value)
    _require(
        not path.is_absolute()
        and not value.startswith("./")
        and "//" not in value
        and "." not in path.parts
        and ".." not in path.parts,
        f"{label} must be relative without aliases",
    )
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise PreventionRegistryError(f"{label} escapes registry root") from exc
    _require(resolved.is_file(), f"{label} does not exist: {value}")
    return resolved


def _evidence(root: Path, value: Any, seen: set[str]) -> None:
    ref = _text(value, "evidence reference")
    _require(ref not in seen, "duplicate evidence reference")
    seen.add(ref)
    _require(ref.count("#") == 1, "evidence reference must be path#anchor")
    path_value, anchor = ref.split("#", 1)
    _text(anchor, "evidence anchor", max_length=180)
    path = _relative_file(root, path_value, "evidence path")
    _require(
        anchor in path.read_text(encoding="utf-8", errors="strict"),
        "evidence anchor is not physically present",
    )


def validate_registry(payload: Mapping[str, Any], *, root: Path | None = None) -> int:
    """Validate and return the number of admitted, evidence-bound entries."""
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
    _require(
        payload.get("known_classes") == sorted(FAILURE_CLASSES), "known failure classes are invalid"
    )
    _require(
        payload.get("unassessed_classes") == ["secret"],
        "unassessed classes must identify the secret coverage gap",
    )
    entries = payload.get("entries")
    _require(
        isinstance(entries, list) and 0 < len(entries) <= 7, "entries are required and bounded"
    )
    ids: set[str] = set()
    classes: set[str] = set()
    seams: set[str] = set()
    resolved_seams: set[tuple[Path, str]] = set()
    evidence_seen: set[str] = set()
    for entry in entries:
        _require(isinstance(entry, Mapping) and set(entry) == ENTRY_KEYS, "entry keys are invalid")
        entry_id = _text(entry.get("id"), "entry id", max_length=64)
        _require(
            IDENTIFIER.fullmatch(entry_id) is not None and entry_id not in ids,
            "duplicate or invalid entry id",
        )
        ids.add(entry_id)
        failure_class = _text(entry.get("failure_class"), "failure class", max_length=40)
        _require(failure_class in FAILURE_CLASSES, f"unsupported failure class: {failure_class}")
        _require(failure_class != "secret", "secret is an unassessed coverage gap")
        _require(failure_class not in classes, "duplicate failure class")
        classes.add(failure_class)
        summary = _text(entry.get("summary"), "summary")
        _require(
            summary.lower().find("authorize") == -1 and summary.lower().find("production") == -1,
            "summary claims authority",
        )
        refs = entry.get("evidence_refs")
        _require(
            isinstance(refs, list) and 0 < len(refs) <= 3, "evidence refs are required and bounded"
        )
        for ref in refs:
            _evidence(root, ref, evidence_seen)
        seam = entry.get("prevention_seam")
        _require(
            isinstance(seam, Mapping) and set(seam) == SEAM_KEYS, "prevention seam is malformed"
        )
        seam_id = _text(seam.get("id"), "seam id", max_length=64)
        _require(
            IDENTIFIER.fullmatch(seam_id) is not None and seam_id not in seams,
            "duplicate or invalid prevention seam",
        )
        seams.add(seam_id)
        kind = _text(seam.get("kind"), "seam kind", max_length=20)
        _require(kind in KINDS, "unsupported prevention seam kind")
        seam_path = _relative_file(root, seam.get("path"), "prevention path")
        anchor = _text(seam.get("anchor"), "prevention anchor", max_length=180)
        seam_text = seam_path.read_text(encoding="utf-8", errors="strict")
        if kind == "instruction":
            _require(
                anchor in seam_text.splitlines(),
                "prevention anchor is not an exact instruction line",
            )
        elif kind in {"test", "command", "fixture"} and seam_path.suffix == ".py":
            _require(
                re.search(
                    rf"^\s*(?:def|class)\s+{re.escape(anchor)}(?:\(|:)", seam_text, re.MULTILINE
                )
                is not None,
                "prevention anchor is not an exact Python identifier",
            )
        else:
            _require(anchor in seam_text, "prevention anchor is not physically present")
        seam_key = (seam_path, anchor)
        _require(seam_key not in resolved_seams, "duplicate resolved prevention seam")
        resolved_seams.add(seam_key)
        _text(entry.get("owner"), "owner", max_length=120)
        _require(entry.get("owner") != "unassigned", "prevention owner is required")
        _require(entry.get("status") in {"active", "retired"}, "invalid prevention status")
        _text(entry.get("removal_condition"), "removal condition")
    _require(
        classes == FAILURE_CLASSES - {"secret"},
        "registry must cover exactly six substantiated recurring classes",
    )
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 1:
        print("usage: validate_codex_dx_failure_prevention.py REGISTRY.json", file=sys.stderr)
        return 2
    path = Path(args[0]).resolve()
    try:
        _require(path.stat().st_size <= 64 * 1024, "registry file exceeds 64KiB")
        count = validate_registry(
            json.loads(path.read_text(encoding="utf-8")), root=path.parents[1]
        )
    except (OSError, json.JSONDecodeError, PreventionRegistryError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {count} recurring failure classes mapped; 1 unassessed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

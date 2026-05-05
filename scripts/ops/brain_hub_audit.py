#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

PHASE_ALIASES = {
    "S": ("phase s", "s phase", "cold-start", "cold start", "seed", "啟動", "冷啟動"),
    "P": ("phase p", "p phase", "plan", "planner", "規劃"),
    "X": ("phase x", "x phase", "research", "x-ray", "研究"),
    "D": ("phase d", "d phase", "diagnose", "diagnosis", "診斷"),
    "R": ("phase r", "r phase", "repair", "修復"),
    "A": ("phase a", "a phase", "audit", "acceptance", "審核", "驗證"),
    "C": ("phase c", "c phase", "crystallize", "learning", "結晶", "學習"),
}
CODE_REF_RE = re.compile(r"(?:^|[`\s(])((?:nexus|scripts|tests|docs|wiki)/[A-Za-z0-9_./\-]+\.(?:py|md|json|yaml|yml))")
STATUS_RE = re.compile(r"^\s*\[PHYSICAL_STATUS:\s*([^\]]+)\]", re.I | re.M)
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.M)


@dataclass(frozen=True)
class HubDocument:
    path: str
    title: str
    phases: list[str] = field(default_factory=list)
    code_refs: list[str] = field(default_factory=list)
    runtime_refs: list[str] = field(default_factory=list)
    test_refs: list[str] = field(default_factory=list)
    manifest_status: str = ""
    physical_status: str = ""
    critical_markers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HubAudit:
    documents: list[HubDocument]
    guidance: dict[str, list[str]]
    failures: list[dict[str, Any]]

    @property
    def passed(self) -> bool:
        return not self.failures


def _title_for(text: str, path: Path) -> str:
    match = HEADING_RE.search(text)
    return match.group(2).strip() if match else path.stem


def _detect_phases(text: str) -> list[str]:
    lower = text.lower()
    phases = []
    for phase, aliases in PHASE_ALIASES.items():
        if any(alias in lower for alias in aliases):
            phases.append(phase)
    return phases


def _critical_markers(text: str) -> list[str]:
    markers = []
    for token in ("CRITICAL", "PENDING", "Ghost Features", "假性對位", "裂縫"):
        if token in text:
            markers.append(token)
    return markers


def _scan_doc(root: Path, path: Path, manifest_entry: dict[str, Any] | None = None) -> HubDocument:
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    status_match = STATUS_RE.search(text)
    refs = sorted({match.group(1) for match in CODE_REF_RE.finditer(text)})
    entry = manifest_entry or {}
    runtime_refs = sorted(str(item) for item in entry.get("runtime_refs", []) if str(item))
    test_refs = sorted(str(item) for item in entry.get("test_refs", []) if str(item))
    return HubDocument(
        path=rel,
        title=_title_for(text, path),
        phases=_detect_phases(text),
        code_refs=refs,
        runtime_refs=runtime_refs,
        test_refs=test_refs,
        manifest_status=str(entry.get("status") or ""),
        physical_status=status_match.group(1).strip() if status_match else "",
        critical_markers=_critical_markers(text),
    )


def _manifest_entries(root: Path, manifest_path: Path | None) -> list[dict[str, Any]]:
    if manifest_path is None:
        return []
    target = manifest_path if manifest_path.is_absolute() else root / manifest_path
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "nexus_brain_hub_manifest.v1":
        raise ValueError("unsupported brain hub manifest schema")
    docs = payload.get("documents", [])
    if not isinstance(docs, list):
        raise ValueError("brain hub manifest documents must be a list")
    return [item for item in docs if isinstance(item, dict)]


def scan_brain_hub(root: Path, paths: list[Path], *, manifest_path: Path | None = None) -> HubAudit:
    docs: list[HubDocument] = []
    failures: list[dict[str, Any]] = []
    manifest_entries = _manifest_entries(root, manifest_path)
    if manifest_path is not None:
        paths = [Path(str(item.get("path") or "")) for item in manifest_entries]
    entries_by_path = {str(item.get("path") or ""): item for item in manifest_entries}
    for base in paths:
        base_path = base if base.is_absolute() else root / base
        candidates = [base_path] if base_path.is_file() else sorted(base_path.glob("*.md"))
        if not base_path.exists():
            failures.append({"path": str(base), "reason": "manifest_document_missing"})
            continue
        for path in candidates:
            if path.suffix.lower() != ".md" or not path.exists():
                continue
            rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            doc = _scan_doc(root, path, entries_by_path.get(rel))
            docs.append(doc)
            if manifest_path is not None:
                if not doc.manifest_status:
                    failures.append({"path": doc.path, "reason": "manifest_status_missing"})
                if not doc.runtime_refs:
                    failures.append({"path": doc.path, "reason": "runtime_refs_missing"})
                if not doc.test_refs:
                    failures.append({"path": doc.path, "reason": "test_refs_missing"})
                for ref in doc.runtime_refs + doc.test_refs:
                    if not (root / ref).exists():
                        failures.append({"path": doc.path, "reason": "manifest_ref_missing", "ref": ref})
            status = doc.physical_status.upper()
            refs_for_status = set(doc.code_refs) | set(doc.runtime_refs) | set(doc.test_refs)
            if status == "PRODUCTION" and not any(ref.startswith(("nexus/", "scripts/", "tests/")) for ref in refs_for_status):
                failures.append(
                    {
                        "path": doc.path,
                        "reason": "production_status_without_runtime_reference",
                        "physical_status": doc.physical_status,
                    }
                )
    guidance = {phase: [] for phase in PHASE_ALIASES}
    for doc in docs:
        for phase in doc.phases:
            guidance[phase].append(doc.path)
    guidance = {phase: sorted(set(files)) for phase, files in guidance.items() if files}
    return HubAudit(documents=docs, guidance=guidance, failures=failures)


def default_paths(root: Path) -> list[Path]:
    wanted = [
        "wiki/arch_diagnosis_brain_hub.md",
        "wiki/critique_brain_hub_alignment_gap.md",
        "wiki/critique_brain_hub_layer3_alignment.md",
        "wiki/NEXUS_EVOLUTION_MANIFESTO_v25.5.md",
        "wiki/NEXUS_GOVERNANCE_EXECUTION_PROTOCOL.md",
        "wiki/NEXUS_EVOLUTION_ONTOLOGY.md",
        "wiki/NEXUS_SWARM_EVOLUTION_PROTOCOL.md",
    ]
    return [Path(item) for item in wanted if (root / item).exists()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Brain Hub docs against runtime references.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--manifest", default="")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    manifest = Path(args.manifest) if args.manifest else None
    paths = [Path(item) for item in args.path] if args.path else default_paths(root)
    audit = scan_brain_hub(root, paths, manifest_path=manifest)
    payload = {"schema_version": "nexus_brain_hub_audit.v1", "passed": audit.passed, **asdict(audit)}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

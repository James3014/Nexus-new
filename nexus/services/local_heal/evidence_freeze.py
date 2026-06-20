"""Clean Evidence Freeze: classify dirty tree and produce freeze report."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


FILE_CATEGORIES = {
    "pycache_build": lambda p: "__pycache__" in p or p.startswith("target/") or p.endswith(".pyc") or ".tmp_build" in p,
    "benchmarks": lambda p: p.startswith("benchmarks/") or "benchmark" in p.lower(),
    "source": lambda p: not p.startswith("tests/") and not p.startswith("scripts/") and not p.startswith("benchmarks/") and p.endswith(".py") and "__pycache__" not in p,
    "tests": lambda p: p.startswith("tests/"),
    "docs_reports": lambda p: p.startswith("docs/") or p.endswith(".md") or "report" in p.lower(),
    "generated_artifacts": lambda p: p.startswith("artifacts/") or p.startswith("nexus_swarm/"),
    "config": lambda p: p.endswith(".json") or p.endswith(".yaml") or p.endswith(".toml") or p.endswith(".ini"),
    "scripts": lambda p: p.startswith("scripts/"),
}


@dataclass(frozen=True)
class FileClassification:
    path: str
    category: str
    can_claim: bool
    reason: str


@dataclass(frozen=True)
class FreezeReport:
    total_dirty: int
    classifications: list[FileClassification] = field(default_factory=list)
    claimable_count: int = 0
    non_claimable_count: int = 0

    def summary(self) -> dict[str, Any]:
        by_category: dict[str, int] = {}
        for fc in self.classifications:
            by_category[fc.category] = by_category.get(fc.category, 0) + 1
        return {
            "total_dirty": self.total_dirty,
            "claimable": self.claimable_count,
            "non_claimable": self.non_claimable_count,
            "by_category": by_category,
        }


def classify_file(path: str) -> FileClassification:
    """Classify a single file into a category."""
    for cat, matcher in FILE_CATEGORIES.items():
        if matcher(path):
            can_claim = cat in ("source", "tests", "scripts")
            reason = "source/test change" if can_claim else f"{cat} — local artifact only"
            return FileClassification(path=path, category=cat, can_claim=can_claim, reason=reason)

    return FileClassification(path=path, category="other", can_claim=False, reason="unclassified — treat as non-claim")


def build_freeze_report(repo_root: str | Path = ".") -> FreezeReport:
    """Build a freeze report from git status."""
    repo_root = Path(repo_root)
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]

    classifications = []
    for line in lines:
        path = line[3:] if len(line) > 3 else line
        classifications.append(classify_file(path))

    claimable = sum(1 for c in classifications if c.can_claim)
    non_claimable = len(classifications) - claimable

    return FreezeReport(
        total_dirty=len(classifications),
        classifications=classifications,
        claimable_count=claimable,
        non_claimable_count=non_claimable,
    )


def build_clean_replay_manifest(
    candidate_ids: list[str],
    freeze_report: FreezeReport,
) -> dict[str, Any]:
    """Build a clean replay manifest for specific candidates."""
    source_changes = [c.path for c in freeze_report.classifications if c.category == "source" and c.can_claim]
    test_changes = [c.path for c in freeze_report.classifications if c.category == "tests" and c.can_claim]

    return {
        "candidates": candidate_ids,
        "replay_constraints": {
            "source_files_changed": source_changes,
            "test_files_changed": test_changes,
            "must_not_include": [
                c.path for c in freeze_report.classifications
                if not c.can_claim
            ],
        },
        "freeze_summary": freeze_report.summary(),
        "public_claim_allowed": False,
        "claim_type": "internal_evidence_only",
    }

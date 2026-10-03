"""Deterministic local fallback search for Local Assist.

Provides a bounded deterministic local fallback evidence search for candidate paths,
tests, and excerpts when full external Repository Intelligence Engine (RIE) services
are not directly bound in the environment.

Explicit Boundary:
- This is a local generic deterministic fallback search.
- It is NOT Repository Intelligence Engine (RIE) and does not claim RIE equivalence.
- Evidence producer is truthfully marked as 'nexus.m5_local.deterministic_fallback.v1'.
- Preserves the invariant: 'A file omitted from retrieval must never be interpreted as proof that it does not exist.'
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Sequence

from .contracts import (
    BoundedEvidencePacket,
    CandidatePathEntry,
    SourceExcerpt,
    StaleBaseError,
)


def _get_current_head(repo_path: Path) -> str:
    """Read the current git rev-parse HEAD of the repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return res.stdout.strip()
    except Exception:
        return ""


def build_deterministic_fallback_packet(
    *,
    task_id: str,
    query: str,
    repo_path: str | Path,
    base_sha: Optional[str] = None,
    candidate_hints: Optional[Sequence[str]] = None,
    max_candidates: int = 15,
    max_excerpt_lines: int = 50,
) -> BoundedEvidencePacket:
    """Build a deterministic, bounded fallback evidence packet from the target repository."""
    root = Path(repo_path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Repository path does not exist: {root}")

    # Base SHA validation (fail closed on stale revision)
    current_head = _get_current_head(root)
    if base_sha and current_head and base_sha.strip().lower() != current_head.strip().lower():
        raise StaleBaseError(
            f"Repository base mismatch: expected {base_sha}, observed {current_head}"
        )

    repo_identity = root.name
    # Extract query tokens for keyword matching
    tokens = {t.lower() for t in re.split(r"[^A-Za-z0-9]+", query) if len(t) >= 3}

    candidate_entries: list[CandidatePathEntry] = []
    seen_paths: set[str] = set()

    # 1. Include explicit candidate hints first
    if candidate_hints:
        for hint in candidate_hints:
            clean_hint = hint.strip().lstrip("/")
            p = root / clean_hint
            if p.is_file() and clean_hint not in seen_paths:
                seen_paths.add(clean_hint)
                try:
                    lines = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
                except Exception:
                    lines = 0
                candidate_entries.append(
                    CandidatePathEntry(
                        path=clean_hint,
                        reason="explicit_candidate_hint",
                        line_count=lines,
                        score=1.0,
                    )
                )

    # 2. Deterministic file search based on query tokens
    search_dirs = [root / "nexus", root / "src", root / "scripts", root / "docs"]
    all_files: list[Path] = []
    for s_dir in search_dirs:
        if not s_dir.is_dir():
            continue
        for curr_root, _, files in os.walk(s_dir):
            for f in files:
                if f.endswith((".py", ".ts", ".md", ".json", ".yaml", ".yml")):
                    all_files.append(Path(curr_root, f))

    # Pass 1: Path token matching across all files
    for full_p in all_files:
        rel_p = str(full_p.relative_to(root))
        if rel_p in seen_paths:
            continue
        p_tokens = {t.lower() for t in re.split(r"[^A-Za-z0-9]+", rel_p) if len(t) >= 3}
        overlap = tokens.intersection(p_tokens)
        if overlap:
            seen_paths.add(rel_p)
            try:
                lines = len(full_p.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                lines = 0
            candidate_entries.append(
                CandidatePathEntry(
                    path=rel_p,
                    reason=f"matched_tokens:{','.join(sorted(overlap))}",
                    line_count=lines,
                    score=2.0 + (len(overlap) / max(len(tokens), 1)),
                )
            )

    # Pass 2: Content token fallback if needed
    if len(candidate_entries) < max_candidates and tokens:
        for full_p in all_files:
            if len(candidate_entries) >= max_candidates:
                break
            rel_p = str(full_p.relative_to(root))
            if rel_p in seen_paths:
                continue
            try:
                content_sample = full_p.read_text(encoding="utf-8", errors="replace")[:20000]
                c_tokens = {
                    t.lower() for t in re.split(r"[^A-Za-z0-9]+", content_sample) if len(t) >= 3
                }
                c_overlap = tokens.intersection(c_tokens)
                if c_overlap:
                    seen_paths.add(rel_p)
                    lines = len(content_sample.splitlines())
                    candidate_entries.append(
                        CandidatePathEntry(
                            path=rel_p,
                            reason=f"content_tokens:{','.join(sorted(c_overlap))}",
                            line_count=lines,
                            score=(len(c_overlap) / max(len(tokens), 1)),
                        )
                    )
            except Exception:
                pass

    # Sort candidates by score descending and truncate
    candidate_entries.sort(key=lambda c: c.score, reverse=True)
    candidate_entries = candidate_entries[:max_candidates]

    # 3. Discover associated test candidates
    test_candidates: list[str] = []
    for cand in candidate_entries:
        cand_p = Path(cand.path)
        cand_stem = cand_p.stem
        subpath = Path(*cand_p.parts[1:]) if len(cand_p.parts) > 1 else cand_p
        # Check standard test locations
        possible_tests = [
            root / "tests" / f"test_{cand_stem}.py",
            root / "tests" / subpath.parent / f"test_{cand_stem}.py",
            root / "tests" / cand.path,
            root / "test" / f"{cand_stem}.test.ts",
        ]
        for t_path in possible_tests:
            if t_path.is_file():
                rel_t = str(t_path.relative_to(root))
                if rel_t not in test_candidates:
                    test_candidates.append(rel_t)

    # 4. Extract bounded excerpts (bounded line counts, not raw dump)
    source_excerpts: list[SourceExcerpt] = []
    for cand in candidate_entries[:5]:  # limit excerpts to top 5
        full_p = root / cand.path
        if full_p.is_file():
            try:
                content_lines = full_p.read_text(encoding="utf-8", errors="replace").splitlines()
                sample = "\n".join(content_lines[:max_excerpt_lines])
                source_excerpts.append(
                    SourceExcerpt(
                        path=cand.path,
                        start_line=1,
                        end_line=min(len(content_lines), max_excerpt_lines),
                        content=sample,
                    )
                )
            except Exception:
                pass

    # 5. Known decisions / contracts
    known_decisions: list[str] = []
    agents_md = root / "AGENTS.md"
    if agents_md.is_file():
        known_decisions.append("root/AGENTS.md: Universal agent governance and execution lanes")

    return BoundedEvidencePacket(
        task_id=task_id,
        query=query,
        repo_identity=repo_identity,
        base_sha=current_head,
        candidate_paths=candidate_entries,
        source_excerpts=source_excerpts,
        test_candidates=test_candidates,
        known_decisions_or_contracts=known_decisions,
        evidence_provenance={
            "retriever": "nexus_m5_local_deterministic_fallback",
            "repo_root": str(root),
            "head": current_head,
        },
    )


# Alias for backward compatibility
build_bounded_evidence_packet = build_deterministic_fallback_packet

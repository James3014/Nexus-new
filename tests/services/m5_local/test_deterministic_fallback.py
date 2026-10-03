"""Unit tests for deterministic local fallback search adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.services.m5_local.contracts import StaleBaseError
from nexus.services.m5_local.deterministic_fallback import (
    build_bounded_evidence_packet,
    build_deterministic_fallback_packet,
)


def test_build_bounded_evidence_packet_localizes_candidates(tmp_path: Path):
    # Setup test repo
    sub = tmp_path / "nexus"
    sub.mkdir()
    f1 = sub / "test_module.py"
    f1.write_text("def solve_problem():\n    return 42\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    t1 = tests_dir / "test_test_module.py"
    t1.write_text("def test_solve(): pass\n", encoding="utf-8")

    packet = build_deterministic_fallback_packet(
        task_id="task-1",
        query="solve_problem",
        repo_path=tmp_path,
    )

    assert packet.task_id == "task-1"
    assert packet.producer == "nexus.m5_local.deterministic_fallback.v1"
    assert any("test_module.py" in c.path for c in packet.candidate_paths)
    assert any("test_test_module.py" in t for t in packet.test_candidates)
    assert len(packet.source_excerpts) > 0
    assert "omitted" in packet.omitted_files_notice.lower()


def test_explicit_candidate_hints(tmp_path: Path):
    f1 = tmp_path / "special.py"
    f1.write_text("SPECIAL = True\n", encoding="utf-8")

    packet = build_bounded_evidence_packet(
        task_id="task-2",
        query="unrelated query",
        repo_path=tmp_path,
        candidate_hints=["special.py"],
    )

    assert any(c.path == "special.py" for c in packet.candidate_paths)
    assert any(c.reason == "explicit_candidate_hint" for c in packet.candidate_paths)


def test_stale_base_sha_fails_closed(tmp_path: Path):
    import subprocess

    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(tmp_path), check=True)
    f = tmp_path / "a.txt"
    f.write_text("hello")
    subprocess.run(["git", "add", "a.txt"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), check=True)

    with pytest.raises(StaleBaseError):
        build_bounded_evidence_packet(
            task_id="task-3",
            query="hello",
            repo_path=tmp_path,
            base_sha="0000000000000000000000000000000000000000",
        )

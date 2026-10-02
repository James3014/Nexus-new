"""Contract tests for RDC/Agy packet-mode reviewer identity and receipts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from nexus.services.agy_reviewer_runtime import (
    AgyReviewError,
    build_review_packet,
    build_review_prompt,
    build_review_receipt,
    collect_review_subject,
    operation_id_for_effect,
    parse_review_verdict,
    subject_matches_packet,
    verify_review_packet,
    verify_review_receipt,
)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "review@example.invalid")
    _git(root, "config", "user.name", "Review Test")
    (root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "a.py")
    _git(root, "commit", "-m", "base")
    _git(root, "remote", "add", "origin", "https://github.com/James3014/Nexus-new.git")
    return root, _git(root, "rev-parse", "HEAD")


def prepare_subject(tmp_path: Path):
    root, base = make_repo(tmp_path)
    (root / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    (root / "new.txt").write_text("new evidence\n", encoding="utf-8")
    contract = tmp_path / "contract.md"
    contract.write_text("require exact subject\n", encoding="utf-8")
    verify = tmp_path / "verify.json"
    verify.write_text('{"tests":"pass"}\n', encoding="utf-8")
    authority = tmp_path / "authority.md"
    authority.write_text("review evidence only\n", encoding="utf-8")
    subject = collect_review_subject(
        root,
        expected_repository="James3014/Nexus-new",
        base_revision=base,
    )
    packet = build_review_packet(
        subject,
        acceptance_contract_file=contract,
        reviewer_role="independent-acceptance",
        verification_receipt_files=[verify],
        authority_excerpt_files=[authority],
    )
    return root, base, contract, verify, authority, subject, packet


def test_packet_binds_exact_subject_and_is_order_stable(tmp_path: Path) -> None:
    root, base = make_repo(tmp_path)
    (root / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    (root / "b.txt").write_text("B\n", encoding="utf-8")
    (root / "c.txt").write_text("C\n", encoding="utf-8")
    contract = tmp_path / "contract.md"
    contract.write_text("contract\n", encoding="utf-8")
    v1 = tmp_path / "v1.txt"
    v2 = tmp_path / "v2.txt"
    v1.write_text("one\n", encoding="utf-8")
    v2.write_text("two\n", encoding="utf-8")

    subject = collect_review_subject(
        root,
        expected_repository="James3014/Nexus-new",
        base_revision=base,
    )
    first = build_review_packet(
        subject,
        acceptance_contract_file=contract,
        reviewer_role="independent-acceptance",
        verification_receipt_files=[v1, v2],
    )
    second = build_review_packet(
        subject,
        acceptance_contract_file=contract,
        reviewer_role="independent-acceptance",
        verification_receipt_files=[v2, v1],
    )

    assert first["candidate_digest"] == second["candidate_digest"]
    assert first["review_effect_id"] == second["review_effect_id"]
    assert first["packet_sha256"] == second["packet_sha256"]
    assert first["changed_paths"] == ["a.py", "b.txt", "c.txt"]
    assert "repo_root" not in first
    assert len(first["repo_root_sha256"]) == 64
    verify_review_packet(first)


def test_contract_or_candidate_change_changes_review_effect(tmp_path: Path) -> None:
    root, base, contract, verify, authority, _, first = prepare_subject(tmp_path)
    contract.write_text("different contract\n", encoding="utf-8")
    second = build_review_packet(
        collect_review_subject(
            root,
            expected_repository="James3014/Nexus-new",
            base_revision=base,
        ),
        acceptance_contract_file=contract,
        reviewer_role="independent-acceptance",
        verification_receipt_files=[verify],
        authority_excerpt_files=[authority],
    )
    assert first["review_effect_id"] != second["review_effect_id"]

    contract.write_text("require exact subject\n", encoding="utf-8")
    (root / "a.py").write_text("VALUE = 3\n", encoding="utf-8")
    third = build_review_packet(
        collect_review_subject(
            root,
            expected_repository="James3014/Nexus-new",
            base_revision=base,
        ),
        acceptance_contract_file=contract,
        reviewer_role="independent-acceptance",
        verification_receipt_files=[verify],
        authority_excerpt_files=[authority],
    )
    assert first["candidate_digest"] != third["candidate_digest"]
    assert first["review_effect_id"] != third["review_effect_id"]


def test_wrong_repository_and_untracked_symlink_fail_closed(tmp_path: Path) -> None:
    root, base = make_repo(tmp_path)
    (root / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(AgyReviewError, match="REPOSITORY_IDENTITY_MISMATCH"):
        collect_review_subject(
            root,
            expected_repository="other/repo",
            base_revision=base,
        )

    target = root / "target.txt"
    target.write_text("secret\n", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to(target.name)
    with pytest.raises(AgyReviewError, match="UNTRACKED_FILE_UNSUPPORTED"):
        collect_review_subject(
            root,
            expected_repository="James3014/Nexus-new",
            base_revision=base,
        )


def test_packet_tamper_is_rejected(tmp_path: Path) -> None:
    _, _, _, _, _, _, packet = prepare_subject(tmp_path)
    tampered = json.loads(json.dumps(packet))
    tampered["tracked_diff"] += "\nTAMPER"
    with pytest.raises(AgyReviewError, match="REVIEW_PACKET_HASH_MISMATCH"):
        verify_review_packet(tampered)


def test_verdict_parser_requires_exactly_one_terminal_line() -> None:
    assert parse_review_verdict("finding\nACCEPT\n") == "ACCEPT"
    with pytest.raises(AgyReviewError, match="REVIEW_VERDICT_NOT_EXACTLY_ONE"):
        parse_review_verdict("looks good")
    with pytest.raises(AgyReviewError, match="REVIEW_VERDICT_NOT_EXACTLY_ONE"):
        parse_review_verdict("ACCEPT\nREPAIR_REQUIRED\n")
    with pytest.raises(AgyReviewError, match="REVIEW_VERDICT_NOT_EXACTLY_ONE"):
        parse_review_verdict("ACCEPT\nACCEPT\n")


def test_prompt_is_packet_only_and_forbids_repo_discovery(tmp_path: Path) -> None:
    _, _, _, _, _, _, packet = prepare_subject(tmp_path)
    prompt = build_review_prompt(packet)
    assert packet["packet_sha256"] in prompt
    assert "Review ONLY the frozen evidence packet" in prompt
    assert "Do not call tools" in prompt
    assert "discover repositories/projects" in prompt


def test_receipt_binds_transport_and_becomes_stale_after_subject_change(
    tmp_path: Path,
) -> None:
    root, _, _, _, _, _, packet = prepare_subject(tmp_path)
    operation = {
        "operation_id": operation_id_for_effect(packet["review_effect_id"]),
        "attempt_id": "attempt_1",
        "status": "COMPLETED",
        "provider": "agy",
        "model": "claude-sonnet-4-6",
        "observed_provider": "agy",
        "observed_model": "claude-sonnet-4-6",
        "provider_session_id": "session-1",
        "finished_at": "2026-10-02T00:00:00+00:00",
    }
    receipt = build_review_receipt(
        packet=packet,
        operation_record=operation,
        reviewer_output="material findings\nACCEPT\n",
        repo_path=root,
    )
    assert receipt["subject_stable"] is True
    assert receipt["review_applicable"] is True
    verify_review_receipt(receipt, packet)

    (root / "a.py").write_text("VALUE = 99\n", encoding="utf-8")
    stable, current = subject_matches_packet(packet, repo_path=root)
    assert stable is False
    assert current.candidate_digest != packet["candidate_digest"]


def test_operation_id_is_stable_prefix_of_effect() -> None:
    effect = "a" * 64
    assert operation_id_for_effect(effect) == "agyop_" + ("a" * 32)
    with pytest.raises(AgyReviewError, match="REVIEW_EFFECT_ID_INVALID"):
        operation_id_for_effect("short")

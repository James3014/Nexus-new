#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


current = load("candidate_acceptance_v4_current", "validate_acceptance_result_v4.py")
legacy = load(
    "candidate_acceptance_v4_legacy",
    "validate_acceptance_result_v4_legacy_20260915.py",
)


class CandidateAcceptanceV4OrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = [
            "README.md",
            "docs/EXTRACTION_STATUS.md",
            "docs/current-source-ownership.json",
        ]

    def entry(self, path: str) -> dict[str, object]:
        return {
            "path": path,
            "change_type": "MODIFY",
            "before_oid": "1" * 40,
            "after_oid": "2" * 40,
            "before_mode": "100644",
            "after_mode": "100755",
        }

    def manifest(self, ordered_paths: list[str]) -> dict[str, object]:
        return {
            "source_tree": "git-tree:" + "a" * 40,
            "target_tree": "git-tree:" + "b" * 40,
            "entries": [self.entry(path) for path in ordered_paths],
        }

    def test_current_order_matches_core_codepoint_order(self) -> None:
        self.assertEqual(
            current._canonical_manifest_path_order(self.paths.copy()),
            sorted(self.paths),
        )

    def test_historical_locale_order_remains_replayable_and_distinct(self) -> None:
        old = legacy._producer_locale_order(self.paths.copy())
        self.assertNotEqual(old, sorted(self.paths))
        self.assertEqual(
            old,
            [
                "docs/current-source-ownership.json",
                "docs/EXTRACTION_STATUS.md",
                "README.md",
            ],
        )

    def test_current_manifest_accepts_canonical_order(self) -> None:
        errors: list[str] = []
        self.assertTrue(
            current._validate_manifest(
                self.manifest(sorted(self.paths)),
                "a" * 40,
                "b" * 40,
                errors,
            )
        )
        self.assertEqual(errors, [])

    def test_current_manifest_rejects_legacy_locale_order(self) -> None:
        errors: list[str] = []
        legacy_manifest = self.manifest(legacy._producer_locale_order(self.paths.copy()))
        self.assertFalse(
            current._validate_manifest(
                legacy_manifest,
                "a" * 40,
                "b" * 40,
                errors,
            )
        )
        self.assertTrue(
            any("canonical Unicode code-point lexical semantics" in error for error in errors)
        )

    def test_core_manifest_hash_uses_canonical_order(self) -> None:
        manifest = self.manifest(sorted(self.paths))
        rows = {row["path"]: row for row in manifest["entries"]}
        expected_value = [
            "nexus.core.git-change-manifest.v1-experimental",
            manifest["source_tree"],
            manifest["target_tree"],
            [
                [
                    rows[path]["path"],
                    rows[path]["change_type"],
                    rows[path]["before_oid"],
                    rows[path]["after_oid"],
                    rows[path]["before_mode"],
                    rows[path]["after_mode"],
                ]
                for path in sorted(self.paths)
            ],
        ]
        self.assertEqual(
            current.core_manifest_hash(manifest),
            current.core_value_hash(expected_value),
        )

    def test_missing_direct_evidence_fails_closed(self) -> None:
        args = SimpleNamespace(
            executor_evidence=None,
            verification_evidence=None,
            v3_validation_report=None,
        )
        errors, warnings = current.validate_physical({"source": {}}, args)
        self.assertEqual(warnings, [])
        self.assertEqual(
            errors,
            ["--executor-evidence is required for v4 physical binding"],
        )



class CandidateAcceptanceV5TransportNeutralTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.counter = 0

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _git(self, repo: Path, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            check=True,
        )
        return proc.stdout.strip()

    def _make_repo(self, *, delete: bool = False, extra_path: bool = False) -> tuple[Path, str, str, str]:
        self.counter += 1
        repo = self.root / f"repo-{self.counter}"
        repo.mkdir()
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.name", "Acceptance Test")
        self._git(repo, "config", "user.email", "acceptance@example.test")
        self._git(repo, "remote", "add", "origin", "https://example.test/owner/repo.git")
        (repo / "a.txt").write_text("one\n", encoding="utf-8")
        card = repo / "tasks" / "test-campaign" / "00-task.md"
        card.parent.mkdir(parents=True)
        card.write_text(
            "# Task Card: goal-standalone-golden-path\n\n"
            "artifact_authority: current\n"
            "task_id: `goal-standalone-golden-path`\n"
            "owner: Test Owner\n"
            "status: ACTIVE\n"
            "commit_required: true\n"
            "candidate_required: true\n"
            "worker_may_approve: false\n"
            "worker_may_integrate: false\n"
            "worker_may_push: false\n"
            "AUTO_CHAIN: false\n\n"
            "## Allowed files\n\n"
            "- `a.txt`\n\n"
            "## Verification commands\n\n"
            "```bash\npython -m pytest -q\n```\n",
            encoding="utf-8",
        )
        self._git(repo, "add", "a.txt", str(card.relative_to(repo)))
        self._git(repo, "commit", "-qm", "base")
        base = self._git(repo, "rev-parse", "HEAD")
        if delete:
            (repo / "a.txt").unlink()
        else:
            (repo / "a.txt").write_text("two\n", encoding="utf-8")
        if extra_path:
            (repo / "b.txt").write_text("out-of-scope\n", encoding="utf-8")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "candidate")
        candidate = self._git(repo, "rev-parse", "HEAD")
        tree = self._git(repo, "rev-parse", "HEAD^{tree}")
        return repo, base, candidate, tree

    def _write_json(self, path: Path, value: dict[str, object]) -> None:
        path.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def _refresh_integrity(self, value: dict[str, object]) -> None:
        value["integrity"] = {"sha256": "0" * 64}
        value["integrity"]["sha256"] = current.canonical_sha256(value)

    def _build_bundle(self, *, delete: bool = False, extra_path: bool = False) -> dict[str, object]:
        repo, base, candidate_sha, tree = self._make_repo(delete=delete, extra_path=extra_path)
        manifest = current._physical_manifest(str(repo), base, candidate_sha)
        changed_paths = [row["path"] for row in manifest["entries"]]
        deleted_paths = [
            row["path"]
            for row in manifest["entries"]
            if row["change_type"] == "DELETE"
        ]
        diff_hash = current.core_manifest_hash(manifest)
        task_id = "goal-standalone-golden-path"
        task_card_path = "tasks/test-campaign/00-task.md"
        task_card_bytes = subprocess.run(
            ["git", "-C", str(repo), "show", f"{base}:{task_card_path}"],
            capture_output=True,
            check=True,
        ).stdout
        task_card_sha = hashlib.sha256(task_card_bytes).hexdigest()
        contract_hash = task_card_sha
        implementer_attempt = "impl-codex-001"
        reviewer_attempt = "review-chatgpt-001"
        created = "2026-09-29T00:00:00+00:00"
        evidence_id = "tnde_" + hashlib.sha256(
            f"{task_id}:{implementer_attempt}:{candidate_sha}:{diff_hash}".encode()
        ).hexdigest()[:32]

        executor: dict[str, object] = {
            "schema": current.V5_DIRECT_SCHEMA,
            "evidence_id": evidence_id,
            "created_at": created,
            "authority": {
                "contract_kind": "TRACKED_TASK_CARD",
                "task_id": task_id,
                "attempt_id": implementer_attempt,
                "task_card_path": task_card_path,
                "task_card_sha256": task_card_sha,
                "allowed_paths": ["a.txt"],
                "deletion_policy": "FORBID",
                "claim_ceiling": "CANDIDATE_READY",
            },
            "execution": {
                "executor_id": "codex-session-001",
                "executor_kind": "coding-agent",
                "transport": "remote-desktop-commander",
                "workspace_root": str(repo),
                "started_at": "2026-09-28T23:50:00+00:00",
                "completed_at": created,
                "state": "completed",
                "terminal_reason": "completed",
            },
            "candidate": {
                "repository_origin": "https://example.test/owner/repo.git",
                "source_commit": base,
                "commit_sha": candidate_sha,
                "tree_sha": tree,
                "changed_paths": changed_paths,
                "deleted_paths": deleted_paths,
                "change_manifest": manifest,
                "diff_hash": diff_hash,
            },
            "claim": {
                "status": "CANDIDATE_READY_PENDING_ACCEPTANCE",
                "claim_ceiling": "CANDIDATE_READY",
                "verified": False,
                "certified": False,
                "accepted": False,
                "approved": False,
                "merged": False,
                "released": False,
                "deployed": False,
                "public_claim_allowed": False,
            },
            "integrity": {"sha256": "0" * 64},
        }
        self._refresh_integrity(executor)

        commands = [
            {
                "id": "focused-tests",
                "cwd": str(repo),
                "argv": ["python", "-m", "pytest", "-q"],
                "result_class": "PASS",
                "exit_code": 0,
                "duration_ms": 25,
                "changed_paths": [],
                "evidence_ref": "review-log:focused-tests",
            }
        ]
        review: dict[str, object] = {
            "schema": current.V5_REVIEW_SCHEMA,
            "review_id": "review-001",
            "created_at": "2026-09-29T00:01:00+00:00",
            "reviewer_id": "review-publisher",
            "reviewer_attempt_id": reviewer_attempt,
            "independence_class": "INDEPENDENT_REVIEWER",
            "repository": {
                "root": str(repo),
                "origin": "https://example.test/owner/repo.git",
                "expected_base_commit": base,
                "candidate_commit_sha": candidate_sha,
                "candidate_tree_sha": tree,
            },
            "commands": commands,
            "provenance": {
                "kind": "GITHUB_ISSUE_COMMENT",
                "repository_full_name": "owner/repo",
                "issue_number": 77,
                "comment_id": 12345,
                "author_login": "review-publisher",
                "review_record_sha256": "0" * 64,
                "body_sha256": "0" * 64,
            },
            "claim": {
                "claim_ceiling": "INDEPENDENT_BEHAVIOR_EVIDENCE_ONLY",
                "certified": False,
                "accepted": False,
                "approved": False,
                "merged": False,
                "released": False,
                "deployed": False,
                "public_claim_allowed": False,
            },
            "integrity": {"sha256": "0" * 64},
        }
        review_record = current._v5_review_record_hash(review)
        review["provenance"]["review_record_sha256"] = review_record
        review_body = (
            f"NEXUS_REVIEW_RECORD_SHA256: {review_record}\n"
            f"NEXUS_CANDIDATE_SHA: {candidate_sha}\n"
            f"NEXUS_TASK_CARD_SHA256: {task_card_sha}\n"
            f"NEXUS_REVIEWER_ATTEMPT: {reviewer_attempt}\n"
            "NEXUS_REVIEWER_ID: review-publisher\n"
        )
        review["provenance"]["body_sha256"] = hashlib.sha256(
            review_body.encode("utf-8")
        ).hexdigest()
        self._refresh_integrity(review)

        artifacts = self.root / f"artifacts-{self.counter}"
        artifacts.mkdir()
        executor_path = artifacts / "executor.json"
        review_path = artifacts / "review.json"
        self._write_json(executor_path, executor)
        self._write_json(review_path, review)

        result: dict[str, object] = {
            "schema": current.V5_SCHEMA,
            "acceptance_id": "acceptance-v5-001",
            "created_at": "2026-09-29T00:02:00+00:00",
            "verdict": "ACCEPT_CANDIDATE",
            "source": {
                "contract_kind": "TRACKED_TASK_CARD",
                "campaign_id": "test-campaign",
                "task_id": task_id,
                "contract_hash": contract_hash,
                "task_card_path": task_card_path,
                "task_card_sha256": task_card_sha,
                "compiled_packet_sha256": None,
                "execution_manifest_sha256": None,
                "implementer_attempt_id": implementer_attempt,
                "reviewer_attempt_id": reviewer_attempt,
                "executor_evidence_kind": current.V5_DIRECT_KIND,
                "executor_evidence_sha256": current.file_sha256(executor_path),
                "verification_evidence_kind": current.V5_REVIEW_KIND,
                "verification_evidence_sha256": current.file_sha256(review_path),
            },
            "repository": {
                "root": str(repo),
                "branch": "candidate",
                "executor_observed_head": base,
                "audit_start_head": candidate_sha,
                "audit_end_head": candidate_sha,
                "expected_base_commit": base,
                "candidate_commit_sha": candidate_sha,
                "candidate_tree_sha": tree,
                "candidate_state_hash": None,
                "candidate_diff_sha256": diff_hash.removeprefix("sha256:"),
                "verified_receipt_hash": None,
                "dirty_state": "clean",
                "candidate_integrated": False,
                "repository_drift_during_audit": False,
            },
            "transport": {
                "mode": "LOCAL_READ_ONLY",
                "server_instance_id": None,
                "canonical_root": None,
                "action_contract_hash": None,
                "tool_manifest_hash": None,
                "full_tool_schema_hash": None,
                "permission_policy_hash": None,
                "lifecycle_revision": None,
                "host_binding_status": "AVAILABLE",
                "verification_surface": "FULL_VERIFY",
                "reload_required": False,
                "action_review_required": False,
                "permission_review_required": False,
                "runtime_source_drift": False,
                "transport_stable": True,
                "start_evidence_ref": "executor-evidence",
                "end_evidence_ref": "review-evidence",
            },
            "axes": {
                name: {
                    "required": True,
                    "verdict": "PASS",
                    "reason": f"{name} independently bound",
                    "evidence_refs": [
                        "review-evidence"
                        if name == "independent_behavior"
                        else "executor-evidence"
                    ],
                }
                for name in current.AXES
            },
            "review": {
                "reviewer_distinct": True,
                "independence_class": "INDEPENDENT_REVIEWER",
                "commands": commands,
                "anti_false_green": "physical Git and independent command evidence rebound",
                "transport_failures": [],
            },
            "approval_readiness": {
                "status": "NOT_EVALUATED",
                "task_pending_acceptance": None,
                "exact_binding_match": None,
                "approval_action_available": None,
                "approval_contract_created": False,
                "candidate_already_approved": False,
                "candidate_already_integrated": False,
                "required_binding_fields": [
                    "contract_kind",
                    "contract_hash",
                    "task_id",
                    "attempt_id",
                    "candidate_commit_sha",
                    "candidate_tree_sha",
                ],
                "blockers": [],
                "evidence_refs": [],
            },
            "approval_boundary": {
                "acceptance_recommendation_only": True,
                "candidate_approved": False,
                "approval_contract_created": False,
                "integrated": False,
                "public_claim_allowed": False,
                "owner_action_required": True,
            },
            "maximum_supportable_claim": (
                "Frozen Candidate evidence supports bounded acceptance recommendation"
            ),
            "next_gate": "OWNER_REVIEW_ACCEPTANCE_RESULT",
            "blockers": [],
            "integrity": {"sha256": "0" * 64},
        }
        self._refresh_integrity(result)
        return {
            "repo": repo,
            "base": base,
            "candidate_sha": candidate_sha,
            "tree": tree,
            "executor": executor,
            "review": review,
            "executor_path": executor_path,
            "review_path": review_path,
            "result": result,
            "review_comment": {
                "body": review_body,
                "user": {"login": "review-publisher"},
                "issue_url": "https://api.github.test/repos/owner/repo/issues/77",
            },
        }

    def _args(self, bundle: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            executor_evidence=bundle["executor_path"],
            verification_evidence=bundle["review_path"],
            v3_validation_report=None,
        )

    def _physical(self, bundle: dict[str, object], args=None):
        if args is None:
            args = self._args(bundle)
        with mock.patch.object(
            current,
            "_v5_fetch_github_comment",
            return_value=bundle["review_comment"],
        ):
            return current.validate_physical(bundle["result"], args)

    def _rewrite_bound(
        self,
        bundle: dict[str, object],
        *,
        executor: bool = False,
        review: bool = False,
    ) -> None:
        result = bundle["result"]
        self.assertIsInstance(result, dict)
        if executor:
            self._refresh_integrity(bundle["executor"])
            self._write_json(bundle["executor_path"], bundle["executor"])
            result["source"]["executor_evidence_sha256"] = current.file_sha256(
                bundle["executor_path"]
            )
        if review:
            self._refresh_integrity(bundle["review"])
            self._write_json(bundle["review_path"], bundle["review"])
            result["source"]["verification_evidence_sha256"] = current.file_sha256(
                bundle["review_path"]
            )
        self._refresh_integrity(result)

    def test_v5_transport_neutral_direct_fixture_passes_physical_binding(self) -> None:
        bundle = self._build_bundle()
        report = current.validate(bundle["result"])
        self.assertTrue(report["valid"], report["errors"])
        errors, warnings = self._physical(bundle)
        self.assertEqual(errors, [])
        self.assertTrue(any("v5 physical Git subject verified" in item for item in warnings))

    def test_v4_still_rejects_transport_neutral_executor_kind(self) -> None:
        bundle = self._build_bundle()
        result = copy.deepcopy(bundle["result"])
        result["schema"] = "nexus.candidate_acceptance.v4"
        self._refresh_integrity(result)
        report = current.validate(result)
        self.assertFalse(report["valid"])
        self.assertTrue(
            any("executor_evidence_kind: invalid" in item for item in report["errors"])
        )

    def test_v5_rejects_devspace_relabeling(self) -> None:
        bundle = self._build_bundle()
        result = bundle["result"]
        result["source"]["executor_evidence_kind"] = "DEVSPACE_DIRECT_EVIDENCE"
        self._refresh_integrity(result)
        report = current.validate(result)
        self.assertFalse(report["valid"])
        self.assertTrue(
            any("TRANSPORT_NEUTRAL_DIRECT_EVIDENCE" in item for item in report["errors"])
        )

    def test_v5_missing_executor_evidence_blocks(self) -> None:
        bundle = self._build_bundle()
        args = self._args(bundle)
        args.executor_evidence = None
        errors, _ = self._physical(bundle, args)
        self.assertEqual(
            errors,
            ["--executor-evidence is required for v5 physical binding"],
        )

    def test_v5_task_card_authority_hash_is_independent(self) -> None:
        bundle = self._build_bundle()
        bundle["executor"]["authority"]["task_card_sha256"] = "0" * 64
        bundle["result"]["source"]["task_card_sha256"] = "0" * 64
        bundle["result"]["source"]["contract_hash"] = "0" * 64
        self._rewrite_bound(bundle, executor=True)
        errors, _ = self._physical(bundle)
        self.assertTrue(
            any("Task Card SHA-256 does not match" in item for item in errors)
        )

    def test_v5_result_subject_mismatches_fail(self) -> None:
        cases = {
            "root": "/tmp/not-the-bound-repository",
            "expected_base_commit": "f" * 40,
            "candidate_commit_sha": "e" * 40,
            "candidate_tree_sha": "d" * 40,
            "candidate_diff_sha256": "c" * 64,
        }
        for key, value in cases.items():
            with self.subTest(key=key):
                bundle = self._build_bundle()
                bundle["result"]["repository"][key] = value
                self._refresh_integrity(bundle["result"])
                errors, _ = self._physical(bundle)
                self.assertTrue(errors, key)

    def test_v5_task_card_binds_scope(self) -> None:
        bundle = self._build_bundle()
        bundle["executor"]["authority"]["allowed_paths"] = ["b.txt"]
        self._rewrite_bound(bundle, executor=True)
        errors, _ = self._physical(bundle)
        self.assertTrue(
            any("Task Card allowed paths do not match" in item for item in errors)
        )

    def test_v5_out_of_scope_path_fails(self) -> None:
        bundle = self._build_bundle(extra_path=True)
        errors, _ = self._physical(bundle)
        self.assertTrue(any("escapes allowed_paths" in item for item in errors))

    def test_v5_forbidden_deletion_fails(self) -> None:
        bundle = self._build_bundle(delete=True)
        errors, _ = self._physical(bundle)
        self.assertTrue(any("forbidden deletions" in item for item in errors))


    def test_v5_tampered_direct_evidence_integrity_fails(self) -> None:
        bundle = self._build_bundle()
        bundle["executor"]["execution"]["executor_id"] = "tampered-session"
        self._write_json(bundle["executor_path"], bundle["executor"])
        bundle["result"]["source"]["executor_evidence_sha256"] = current.file_sha256(
            bundle["executor_path"]
        )
        self._refresh_integrity(bundle["result"])
        errors, _ = self._physical(bundle)
        self.assertTrue(any("integrity mismatch" in item for item in errors))

    def test_v5_review_bound_to_wrong_candidate_fails(self) -> None:
        bundle = self._build_bundle()
        bundle["review"]["repository"]["candidate_commit_sha"] = bundle["base"]
        self._rewrite_bound(bundle, review=True)
        errors, _ = self._physical(bundle)
        self.assertTrue(any("candidate_commit_sha mismatch" in item for item in errors))

    def test_v5_same_implementer_and_reviewer_attempt_fails(self) -> None:
        bundle = self._build_bundle()
        bundle["result"]["source"]["reviewer_attempt_id"] = bundle["result"]["source"][
            "implementer_attempt_id"
        ]
        self._refresh_integrity(bundle["result"])
        report = current.validate(bundle["result"])
        self.assertFalse(report["valid"])
        self.assertTrue(
            any("must differ from implementer" in item for item in report["errors"])
        )

    def test_v5_review_provenance_marker_mismatch_fails(self) -> None:
        bundle = self._build_bundle()
        bundle["review_comment"]["body"] = "wrong review marker\n"
        errors, _ = self._physical(bundle)
        self.assertTrue(
            any("review provenance verification failed" in item for item in errors)
        )

    def test_v5_review_author_mismatch_fails(self) -> None:
        bundle = self._build_bundle()
        bundle["review_comment"]["user"]["login"] = "different-reviewer"
        errors, _ = self._physical(bundle)
        self.assertTrue(
            any("review provenance verification failed" in item for item in errors)
        )

    def test_v5_rejects_owner_inline_authority(self) -> None:
        bundle = self._build_bundle()
        bundle["result"]["source"]["contract_kind"] = "OWNER_INLINE"
        bundle["executor"]["authority"]["contract_kind"] = "OWNER_INLINE"
        self._rewrite_bound(bundle, executor=True)
        report = current.validate(bundle["result"])
        self.assertFalse(report["valid"])
        self.assertTrue(
            any("requires TRACKED_TASK_CARD" in item for item in report["errors"])
        )

    def test_v5_claim_escalation_fails(self) -> None:
        bundle = self._build_bundle()
        bundle["executor"]["claim"]["approved"] = True
        self._rewrite_bound(bundle, executor=True)
        errors, _ = self._physical(bundle)
        self.assertTrue(any("illegally asserts approved" in item for item in errors))


if __name__ == "__main__":
    unittest.main()

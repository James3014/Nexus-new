import json
import subprocess
import sys
from pathlib import Path

from scripts.ops.agent_protocol_check import check_protocol, evaluate_completion_snapshot

ROOT = Path(__file__).resolve().parents[2]
CURRENT_REQUIRED_TERMS = (
    "Direct authority",
    "Governed authority",
    "Completion requires behavioral evidence",
    "Report evidence in the final response",
    "docs/agents/TASK_EXECUTION_CONTRACT.md",
    "docs/agents/LEARNING_WRITEBACK_OVERLAY.md",
    "CapabilityPlanner",
)


def _write_agents(path: Path, terms=CURRENT_REQUIRED_TERMS):
    path.write_text("\n".join(terms), encoding="utf-8")


def _write_contract(path: Path, *, forbidden=None, allowed=None, max_files=10):
    forbidden = forbidden or [".obsidian/"]
    allowed = allowed or ["."]
    path.write_text(
        json.dumps({
            "required_terms": list(CURRENT_REQUIRED_TERMS),
            "boundaries": {
                "allowed_paths": allowed,
                "forbidden_paths": forbidden,
                "max_files_touched": max_files,
            },
        }),
        encoding="utf-8",
    )


def _write_overlay_card(path: Path, *, forbidden=None, allowed=None, max_files=10):
    forbidden = forbidden or []
    allowed = allowed or ["scripts/"]
    path.write_text(
        "## Machine policy overlay\n\n```json\n"
        + json.dumps({
            "allowed_paths": allowed,
            "forbidden_paths": forbidden,
            "max_files_touched": max_files,
        })
        + "\n```\n",
        encoding="utf-8",
    )


def test_repository_contract_accepts_current_compact_agents(monkeypatch):
    monkeypatch.chdir(ROOT)

    assert check_protocol(contract_path=ROOT / "scripts/ops/agent_protocol_contract.json") == 0


def test_protocol_missing_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert check_protocol(contract_path=tmp_path / "contract.json") == 1


def test_protocol_missing_terms(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md", CURRENT_REQUIRED_TERMS[:1])
    _write_contract(tmp_path / "contract.json")
    assert check_protocol(contract_path=tmp_path / "contract.json") == 1


def test_protocol_check_files_forbidden(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    _write_contract(tmp_path / "contract.json", forbidden=[".obsidian/", "secret/"])
    # Hit forbidden
    assert (
        check_protocol(check_files=[".obsidian/config"], contract_path=tmp_path / "contract.json")
        == 1
    )
    assert check_protocol(check_files=["secret/key"], contract_path=tmp_path / "contract.json") == 1


def test_protocol_check_files_too_many(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    _write_contract(tmp_path / "contract.json", max_files=2)
    assert (
        check_protocol(
            check_files=["a.txt", "b.txt", "c.txt"], contract_path=tmp_path / "contract.json"
        )
        == 1
    )


def test_protocol_check_files_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    _write_contract(tmp_path / "contract.json")
    assert (
        check_protocol(check_files=["a.txt", "b.txt"], contract_path=tmp_path / "contract.json")
        == 0
    )


def test_protocol_check_files_strict_boundary_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    _write_contract(tmp_path / "contract.json", allowed=["scripts/ops/"])
    assert (
        check_protocol(
            check_files=["nexus_wiki_vault/00_Home/System Overview.md"],
            strict=True,
            contract_path=tmp_path / "contract.json",
        )
        == 1
    )


def test_protocol_missing_baseline_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    assert check_protocol(contract_path=tmp_path / "missing.json") == 1


def test_protocol_malformed_baseline_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    contract = tmp_path / "contract.json"
    contract.write_text("{not-json")
    assert check_protocol(contract_path=contract) == 1


def test_protocol_task_card_overlay_narrows_baseline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_agents(tmp_path / "AGENTS.md")
    contract = tmp_path / "contract.json"
    _write_contract(contract, allowed=["."], forbidden=["packages/"], max_files=5)
    card = tmp_path / "card.md"
    _write_overlay_card(card, allowed=["scripts/"], forbidden=["scripts/private/"], max_files=2)

    assert (
        check_protocol(
            check_files=["scripts/ops/check.py"],
            strict=True,
            contract_path=contract,
            task_card_path=card,
        )
        == 0
    )
    assert (
        check_protocol(
            check_files=["docs/plan.md"],
            strict=True,
            contract_path=contract,
            task_card_path=card,
        )
        == 1
    )
    assert (
        check_protocol(
            check_files=["scripts/private/key.txt"],
            contract_path=contract,
            task_card_path=card,
        )
        == 1
    )
    assert (
        check_protocol(
            check_files=["scripts/a.py", "scripts/b.py", "scripts/c.py"],
            contract_path=contract,
            task_card_path=card,
        )
        == 1
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _completion_repo(tmp_path: Path) -> dict[str, str | Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "completion@example.test")
    _git(repo, "config", "user.name", "Completion Gate")
    _git(repo, "remote", "add", "nexus-new", "https://github.com/James3014/Nexus-new.git")
    (repo / "state.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "state.txt")
    _git(repo, "commit", "-m", "base")

    _git(repo, "checkout", "-b", "candidate")
    (repo / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    _git(repo, "add", "candidate.txt")
    _git(repo, "commit", "-m", "candidate")
    candidate = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "main")
    (repo / "state.txt").write_text("main moved\n", encoding="utf-8")
    _git(repo, "add", "state.txt")
    _git(repo, "commit", "-m", "main moved")
    _git(repo, "merge", "--no-ff", "candidate", "-m", "merge candidate")
    main = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/nexus-new/main", main)

    return {
        "repo": repo,
        "candidate": candidate,
        "main": main,
        "tree": _git(repo, "rev-parse", "HEAD^{tree}"),
    }


def _completion_snapshot(history: dict[str, str | Path]) -> dict:
    candidate = str(history["candidate"])
    main = str(history["main"])
    return {
        "schema": "nexus.issue_completion_snapshot.v1",
        "repository": "James3014/Nexus-new",
        "issue": {
            "number": 122,
            "contract_revision": "c" * 64,
            "latest_comment_id": "IC_current",
        },
        "candidate": {"issue_number": 122, "pr_number": 177, "head_sha": candidate},
        "pull_request": {
            "number": 177,
            "issue_number": 122,
            "head_sha": candidate,
            "merge_commit_sha": main,
            "state": "MERGED",
        },
        "current_main": {"head_sha": main, "tree_sha": str(history["tree"])},
        "required_evidence_ids": ["post-merge-verifier"],
        "evidence": [
            {
                "id": "post-merge-verifier",
                "kind": "POST_MERGE_CURRENT_MAIN",
                "status": "PASS",
                "bound_sha": main,
                "bound_tree_sha": str(history["tree"]),
            }
        ],
        "hard_prerequisites": [],
        "original_contract_satisfied": True,
        "contract_delta_required": False,
        "distinct_follow_up_required": False,
        "existing_durable_owner_checked": True,
        "requested_downstream_ready": True,
    }


def _completion_bindings(snapshot: dict) -> dict:
    return {
        "repository": snapshot["repository"],
        "issue_number": snapshot["issue"]["number"],
        "issue_contract_revision": snapshot["issue"]["contract_revision"],
        "latest_comment_id": snapshot["issue"]["latest_comment_id"],
        "pr_number": snapshot["pull_request"]["number"],
        "candidate_head_sha": snapshot["candidate"]["head_sha"],
        "merge_commit_sha": snapshot["pull_request"]["merge_commit_sha"],
        "main_ref": "refs/remotes/nexus-new/main",
        "remote_url": "https://github.com/James3014/Nexus-new.git",
        "current_main_head_sha": snapshot["current_main"]["head_sha"],
        "current_main_tree_sha": snapshot["current_main"]["tree_sha"],
        "required_evidence_ids": list(snapshot["required_evidence_ids"]),
        "required_predecessors": list(snapshot["hard_prerequisites"]),
    }


def _evaluate(snapshot: dict, history: dict[str, str | Path], *, expected: dict | None = None):
    return evaluate_completion_snapshot(
        snapshot,
        repo_root=Path(history["repo"]),
        main_ref="refs/remotes/nexus-new/main",
        expected_bindings=_completion_bindings(expected or snapshot),
    )


def test_completion_snapshot_binds_issue_candidate_merge_and_current_main(tmp_path):
    history = _completion_repo(tmp_path)

    result = _evaluate(_completion_snapshot(history), history)

    assert result == {
        "disposition": "DONE_NO_FOLLOW_UP",
        "terminal": True,
        "downstream_ready": True,
        "failures": [],
    }


def test_completion_snapshot_stale_main_fails_closed(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot["current_main"]["head_sha"] = "a" * 40

    result = _evaluate(snapshot, history)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert result["terminal"] is False
    assert result["downstream_ready"] is False
    assert "current_main_head_mismatch" in result["failures"]


def test_completion_snapshot_rejects_wrong_pr_candidate_attribution(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot["candidate"]["issue_number"] = 119
    snapshot["pull_request"]["head_sha"] = "b" * 40

    result = _evaluate(snapshot, history)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "candidate_issue_mismatch" in result["failures"]
    assert "candidate_pr_head_mismatch" in result["failures"]


def test_completion_snapshot_rejects_wrong_repository(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot["repository"] = "James3014/Nexus"

    expected = _completion_snapshot(history)
    result = _evaluate(snapshot, history, expected=expected)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "repository_identity_mismatch" in result["failures"]


def test_completion_snapshot_missing_required_evidence_fails_closed(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot["evidence"] = []

    result = _evaluate(snapshot, history)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "required_evidence_missing:post-merge-verifier" in result["failures"]
    assert "post_merge_current_main_evidence_missing" in result["failures"]


def test_completion_snapshot_does_not_unlock_downstream_for_open_predecessor(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot["original_contract_satisfied"] = False
    snapshot["requested_downstream_ready"] = True
    snapshot["hard_prerequisites"] = [
        {
            "issue_number": 29,
            "disposition": "KEEP_OPEN",
            "bound_main_sha": history["main"],
        }
    ]

    result = _evaluate(snapshot, history)

    assert result["disposition"] == "KEEP_OPEN"
    assert result["terminal"] is False
    assert result["downstream_ready"] is False
    assert "predecessor_not_terminal:29" in result["failures"]


def test_completion_snapshot_blocks_stale_predecessor_revision(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot["hard_prerequisites"] = [
        {
            "issue_number": 29,
            "disposition": "DONE_NO_FOLLOW_UP",
            "bound_main_sha": "d" * 40,
        }
    ]

    result = _evaluate(snapshot, history)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert result["terminal"] is False
    assert "predecessor_revision_mismatch:29" in result["failures"]


def test_completion_snapshot_requires_tree_bound_post_merge_evidence(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot["evidence"][0]["bound_tree_sha"] = "e" * 40

    result = _evaluate(snapshot, history)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "post_merge_current_main_evidence_missing" in result["failures"]


def test_completion_snapshot_classifies_contract_delta_and_distinct_follow_up(tmp_path):
    history = _completion_repo(tmp_path)
    delta = _completion_snapshot(history)
    delta["contract_delta_required"] = True
    follow_up = _completion_snapshot(history)
    follow_up["distinct_follow_up_required"] = True

    delta_result = _evaluate(delta, history)
    follow_up_result = _evaluate(follow_up, history)

    assert delta_result["disposition"] == "CONTRACT_DELTA"
    assert delta_result["terminal"] is False
    assert follow_up_result["disposition"] == "FOLLOW_UP_REQUIRED"
    assert follow_up_result["terminal"] is True


def test_completion_snapshot_rejects_self_bound_feature_branch_as_current_main(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    repo = Path(history["repo"])
    _git(repo, "checkout", "-b", "feature-after-main")
    (repo / "branch-only.txt").write_text("not main\n", encoding="utf-8")
    _git(repo, "add", "branch-only.txt")
    _git(repo, "commit", "-m", "branch only")
    snapshot["current_main"] = {
        "head_sha": _git(repo, "rev-parse", "HEAD"),
        "tree_sha": _git(repo, "rev-parse", "HEAD^{tree}"),
    }
    snapshot["pull_request"]["merge_commit_sha"] = snapshot["current_main"]["head_sha"]

    result = _evaluate(snapshot, history)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "current_main_head_mismatch" in result["failures"]


def test_completion_snapshot_rejects_stale_issue_and_consistent_wrong_pr(tmp_path):
    history = _completion_repo(tmp_path)
    expected = _completion_snapshot(history)
    snapshot = _completion_snapshot(history)
    snapshot["issue"]["contract_revision"] = "d" * 64
    snapshot["issue"]["latest_comment_id"] = "IC_stale"
    snapshot["candidate"]["pr_number"] = 999
    snapshot["pull_request"]["number"] = 999

    result = _evaluate(snapshot, history, expected=expected)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "issue_contract_revision_mismatch" in result["failures"]
    assert "latest_issue_comment_mismatch" in result["failures"]
    assert "pull_request_identity_mismatch" in result["failures"]


def test_completion_snapshot_rejects_missing_pr_identity(tmp_path):
    history = _completion_repo(tmp_path)
    expected = _completion_snapshot(history)
    snapshot = _completion_snapshot(history)
    snapshot["candidate"].pop("pr_number")
    snapshot["pull_request"].pop("number")

    result = _evaluate(snapshot, history, expected=expected)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "pull_request_number_invalid" in result["failures"]


def test_completion_snapshot_rejects_omitted_required_predecessor(tmp_path):
    history = _completion_repo(tmp_path)
    expected = _completion_snapshot(history)
    expected["hard_prerequisites"] = [
        {
            "issue_number": 29,
            "disposition": "DONE_NO_FOLLOW_UP",
            "bound_main_sha": history["main"],
        }
    ]
    snapshot = _completion_snapshot(history)

    result = _evaluate(snapshot, history, expected=expected)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "required_predecessor_set_mismatch" in result["failures"]


def test_completion_snapshot_rejects_duplicate_evidence_and_nonboolean_downstream(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot["evidence"].append(dict(snapshot["evidence"][0]))
    snapshot["requested_downstream_ready"] = "false"

    result = _evaluate(snapshot, history)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "duplicate_evidence_id:post-merge-verifier" in result["failures"]
    assert "completion_semantic_flags_invalid" in result["failures"]


def test_completion_snapshot_rejects_contradictory_completion_signals(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot["contract_delta_required"] = True
    snapshot["distinct_follow_up_required"] = True

    result = _evaluate(snapshot, history)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "completion_signals_contradictory" in result["failures"]


def test_completion_snapshot_rejects_wrong_main_ref_and_fabricated_commit_identities(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    bindings = _completion_bindings(snapshot)
    repo = Path(history["repo"])
    _git(repo, "checkout", "-b", "wrong-main")
    (repo / "wrong-main.txt").write_text("wrong\n", encoding="utf-8")
    _git(repo, "add", "wrong-main.txt")
    _git(repo, "commit", "-m", "wrong main")
    wrong_head = _git(repo, "rev-parse", "HEAD")
    wrong_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    snapshot["candidate"]["head_sha"] = history["main"]
    snapshot["pull_request"]["head_sha"] = history["main"]
    snapshot["pull_request"]["merge_commit_sha"] = wrong_head
    snapshot["current_main"] = {"head_sha": wrong_head, "tree_sha": wrong_tree}
    snapshot["evidence"][0]["bound_sha"] = wrong_head
    snapshot["evidence"][0]["bound_tree_sha"] = wrong_tree

    result = evaluate_completion_snapshot(
        snapshot,
        repo_root=repo,
        main_ref="wrong-main",
        expected_bindings=bindings,
    )

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "default_main_ref_invalid" in result["failures"]
    assert "candidate_head_identity_mismatch" in result["failures"]
    assert "merge_commit_identity_mismatch" in result["failures"]


def test_completion_snapshot_rejects_extra_evidence_and_forged_predecessor_receipt(tmp_path):
    history = _completion_repo(tmp_path)
    expected = _completion_snapshot(history)
    expected["hard_prerequisites"] = [
        {
            "issue_number": 29,
            "disposition": "DONE_NO_FOLLOW_UP",
            "bound_main_sha": history["main"],
            "receipt_sha": "a" * 64,
        }
    ]
    snapshot = _completion_snapshot(history)
    snapshot["hard_prerequisites"] = [
        {
            "issue_number": 29,
            "disposition": "DONE_NO_FOLLOW_UP",
            "bound_main_sha": history["main"],
            "receipt_sha": "b" * 64,
        }
    ]
    snapshot["evidence"].append({"id": "unexpected", "status": "PASS"})

    result = _evaluate(snapshot, history, expected=expected)

    assert result["disposition"] == "BLOCKED_EVIDENCE"
    assert "evidence_set_mismatch" in result["failures"]
    assert "predecessor_binding_mismatch:29" in result["failures"]


def test_completion_snapshot_cli_requires_fresh_bindings_and_explicit_main_ref(tmp_path):
    history = _completion_repo(tmp_path)
    snapshot = _completion_snapshot(history)
    snapshot_path = tmp_path / "snapshot.json"
    bindings_path = tmp_path / "bindings.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    bindings_path.write_text(json.dumps(_completion_bindings(snapshot)), encoding="utf-8")
    script = ROOT / "scripts/ops/agent_protocol_check.py"

    missing_bindings = subprocess.run(
        [sys.executable, str(script), "--completion-snapshot", str(snapshot_path)],
        cwd=history["repo"],
        capture_output=True,
        text=True,
        check=False,
    )
    valid = subprocess.run(
        [
            sys.executable,
            str(script),
            "--completion-snapshot",
            str(snapshot_path),
            "--completion-bindings",
            str(bindings_path),
            "--main-ref",
            "refs/remotes/nexus-new/main",
        ],
        cwd=history["repo"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert missing_bindings.returncode == 1
    assert "Completion bindings are required" in missing_bindings.stdout
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["disposition"] == "DONE_NO_FOLLOW_UP"

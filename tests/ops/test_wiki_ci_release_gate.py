import json
from pathlib import Path

from scripts.ops import wiki_ci_release_gate as gate


def test_receipt_has_commit_identity_and_fail_closed_evidence(monkeypatch, tmp_path: Path):
    repo = tmp_path / "repo"
    output = repo / ".nexus" / "reports"
    (repo / gate.GENERATED_DIR).mkdir(parents=True)
    fingerprint = "f" * 64
    for name in gate.ARTIFACTS:
        payload = {"source_fingerprint": fingerprint} if name in {
            "agent-index.json", "wikilink-graph.json", "unresolved-link-inventory.json"
        } else {}
        (repo / gate.GENERATED_DIR / name).write_text(json.dumps(payload) + "\n", encoding="utf-8")

    monkeypatch.setattr(gate, "_git_head", lambda root: "a" * 40)
    monkeypatch.setattr(gate, "_run_command", lambda root, argv, timeout=180: {
        "command": argv, "status": "PASS", "exit_code": 0, "stdout": "", "stderr": ""
    })
    monkeypatch.setattr(gate, "_authority_metrics", lambda root: (
        {"name": "wiki_required_authority_labels", "status": "PASS", "reason": ""},
        {"required_count": 1, "resolved_count": 1},
    ))
    monkeypatch.setattr(gate, "_coverage_metrics", lambda root: (
        {"name": "wiki_coverage", "status": "PASS", "reason": ""},
        {"coverage_ratio": "100.00%"},
    ))
    monkeypatch.setattr(gate, "_freshness_metrics", lambda root: (
        {"name": "wiki_current_authority_source_paths", "status": "PASS", "reason": ""},
        {"error_count": 0},
    ))
    monkeypatch.setattr(gate, "_current_link_metrics", lambda root: (
        {"name": "wiki_current_authority_links", "status": "PASS", "reason": ""},
        {"current_unresolved": 0},
    ))
    monkeypatch.setattr(gate, "_runtime_metrics", lambda root: (
        {"name": "knowledge_agent_runtime_integration", "status": "PASS", "reason": ""},
        {"status": "PASS", "blockers": []},
    ))

    (repo / gate.GENERATED_DIR / "unresolved-link-inventory.json").write_text(
        json.dumps({"source_fingerprint": fingerprint, "governance_summary": {"disposition_counts": {}}, "category_counts": {}}),
        encoding="utf-8",
    )
    receipt = gate.run_gate(repo, output)

    assert receipt["gate_verdict"] == "PASS"
    assert receipt["commit_sha"] == "a" * 40
    assert receipt["receipt_path"] == str((output / "wiki-ci-release-governance-receipt.json").resolve())
    assert receipt["evidence_path"] == str((output / "wiki-ci-release-governance-evidence.json").resolve())
    assert json.loads(Path(receipt["evidence_path"]).read_text())["schema"] == gate.EVIDENCE_SCHEMA


def test_failed_critical_command_blocks_and_records_reason(monkeypatch, tmp_path: Path):
    repo = tmp_path / "repo"
    output = repo / "receipt"
    (repo / gate.GENERATED_DIR).mkdir(parents=True)
    fingerprint = "f" * 64
    for name in gate.ARTIFACTS:
        payload = {"source_fingerprint": fingerprint} if name in {
            "agent-index.json", "wikilink-graph.json", "unresolved-link-inventory.json"
        } else {}
        (repo / gate.GENERATED_DIR / name).write_text(json.dumps(payload) + "\n", encoding="utf-8")
    (repo / gate.GENERATED_DIR / "unresolved-link-inventory.json").write_text(
        json.dumps({"governance_summary": {}, "category_counts": {}}), encoding="utf-8"
    )

    def fail_index(root, argv, timeout=180):
        return {"command": argv, "status": "BLOCK", "exit_code": 1, "stdout": "drift", "stderr": ""}

    monkeypatch.setattr(gate, "_run_command", fail_index)
    monkeypatch.setattr(gate, "_git_head", lambda root: "b" * 40)
    monkeypatch.setattr(gate, "_authority_metrics", lambda root: ({"name": "authority", "status": "PASS", "reason": ""}, {}))
    monkeypatch.setattr(gate, "_coverage_metrics", lambda root: ({"name": "coverage", "status": "PASS", "reason": ""}, {}))
    monkeypatch.setattr(gate, "_freshness_metrics", lambda root: ({"name": "freshness", "status": "PASS", "reason": ""}, {}))
    monkeypatch.setattr(gate, "_current_link_metrics", lambda root: ({"name": "links", "status": "PASS", "reason": ""}, {}))
    monkeypatch.setattr(gate, "_runtime_metrics", lambda root: ({"name": "runtime", "status": "PASS", "reason": ""}, {}))

    receipt = gate.run_gate(repo, output)

    assert receipt["gate_verdict"] == "BLOCK"
    assert any(reason.startswith("wiki_index_deterministic:") for reason in receipt["missing_evidence_reasons"])

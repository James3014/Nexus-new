import json
import subprocess
from pathlib import Path

from scripts.ops import ci_gate


def _mock_git_ls_files(monkeypatch, tracked_files):
    class MockRes:
        def __init__(self, stdout):
            self.stdout = stdout
            self.returncode = 0

    def _run(cmd, cwd=None, capture_output=False, text=False):
        if cmd == ["git", "ls-files"]:
            return MockRes("\n".join(tracked_files))
        return MockRes("")

    monkeypatch.setattr(subprocess, "run", _run)


def test_delivery_tracked_accepts_dict_artifact_entries(tmp_path, monkeypatch):
    evidence = tmp_path / "hallucination_evidence.json"
    payload = {
        "evidence_bundle": {
            "code_artifacts": [
                {"file_path": "nexus/engine/pipeline_repair.py", "modification_type": "modified"}
            ]
        }
    }
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    _mock_git_ls_files(monkeypatch, ["nexus/engine/pipeline_repair.py"])
    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)

    assert ci_gate.run_delivery_tracked_check(evidence_path=str(evidence), dry_run=True) is True


def test_delivery_tracked_accepts_mixed_artifact_shapes(tmp_path, monkeypatch):
    evidence = tmp_path / "hallucination_evidence.json"
    payload = {
        "evidence_bundle": {
            "code_artifacts": [
                "nexus/core/state_contracts.py",
                {"file_path": "nexus/core/skill_outcomes.py", "modification_type": "modified"},
            ]
        }
    }
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    _mock_git_ls_files(monkeypatch, ["nexus/core/state_contracts.py", "nexus/core/skill_outcomes.py"])
    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)

    assert ci_gate.run_delivery_tracked_check(evidence_path=str(evidence), dry_run=True) is True

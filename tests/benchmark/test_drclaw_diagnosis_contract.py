import importlib.util
from pathlib import Path

from scripts.drclaw_diagnosis import DrClawDiagnosis


def test_drclaw_diagnosis_behavior(tmp_path: Path):
    diag = DrClawDiagnosis(worktree_path=str(tmp_path))
    assert diag.worktree_path == str(tmp_path.resolve())

    # Test report parsing
    report = "**High** Security vulnerability found in authentication\n**Low** Code style note"
    parsed = diag._parse_codex_report(report)
    assert parsed["quality"] == "S"
    assert parsed["confidence"] == 0.98
    assert "Codex 偵測到 2 個關鍵缺陷" in parsed["root_cause"]

    # Test empty report parsing fallback
    empty_parsed = diag._parse_codex_report("no keywords")
    assert empty_parsed["quality"] == "B"
    assert "無法從報告中提取明確 Finding" in empty_parsed["root_cause"]


def test_rebuild_bde_audit_wiring():
    repo_root = Path(__file__).resolve().parents[2]
    audit_script = repo_root / "scripts" / "bench" / "rebuild_bde_audit.py"
    assert audit_script.exists()

    spec = importlib.util.spec_from_file_location("rebuild_bde_audit", audit_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Prove canonical 34 capabilities contains drclaw_diagnosis path for xray
    capabilities = getattr(module, "CANONICAL_34_CAPABILITIES", {})
    xray = capabilities.get("xray", {})
    assert xray.get("module_path") == "scripts/drclaw_diagnosis.py"

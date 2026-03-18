import importlib.util
from pathlib import Path


def _load_ci_gate_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "ci_gate.py"
    spec = importlib.util.spec_from_file_location("ci_gate_module", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_compute_phantom_success_detects_missing_apply_on_patch():
    mod = _load_ci_gate_module()
    rows = [
        {
            "status": "PASS",
            "patch_generated": "true",
            "patch_apply_success": "false",
            "no_change_reason": "",
        }
    ]
    out = mod.compute_phantom_success(rows)
    assert out["phantom_count"] == 1


def test_compute_phantom_success_accepts_no_change_reason():
    mod = _load_ci_gate_module()
    rows = [
        {
            "status": "PASS",
            "patch_generated": "false",
            "patch_apply_success": "",
            "no_change_reason": "Docs-only normalization; no code change required.",
        }
    ]
    out = mod.compute_phantom_success(rows)
    assert out["phantom_count"] == 0
    assert out["inconclusive_count"] == 0

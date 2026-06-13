
import json
import pytest
import jsonschema
from pathlib import Path
import subprocess

SCHEMA_PATH = Path("schemas/s2t_memory_sidecar_checkpoint.schema.json")
FIXTURE_DIR = Path("tests/fixtures/s2t_memory_sidecar")

@pytest.fixture
def schema():
    with SCHEMA_PATH.open("r") as f:
        return json.load(f)

@pytest.mark.parametrize("fixture_name", [
    "f1_success_ready", "f2_tests_red", "f3_missing_tasklist", 
    "f4_model_not_called", "f5_receipt_mismatch", "f6_dirty_workspace",
    "f7_false_reject", "f8_semantic_rejected", "f9_rollback",
    "f10_insufficient_evidence"
])
def test_sidecar_against_golden_fixtures(fixture_name, schema, tmp_path):
    f_dir = FIXTURE_DIR / fixture_name
    output_file = tmp_path / f"{fixture_name}_checkpoint.jsonl"
    
    cmd = [
        "python3", "scripts/bench/s2t_memory_sidecar_shadow.py",
        "--task-id", fixture_name,
        "--output", str(output_file),
        "--mock" # Use mock for infrastructure test
    ]
    
    # Add artifact paths if they exist
    if (f_dir / "receipt.json").exists(): cmd.extend(["--receipt", str(f_dir / "receipt.json")])
    if (f_dir / "execution.log").exists(): cmd.extend(["--log", str(f_dir / "execution.log")])
    if (f_dir / "git_diff.stat").exists(): cmd.extend(["--git-diff-stat", str(f_dir / "git_diff.stat")])
    if (f_dir / "pytest.log").exists(): cmd.extend(["--test-output", str(f_dir / "pytest.log")])
    if (f_dir / "plan.md").exists(): cmd.extend(["--plan", str(f_dir / "plan.md")])
    
    subprocess.run(cmd, check=True)
    
    assert output_file.exists()
    with output_file.open("r") as f:
        data = json.loads(f.readline())
        
    checkpoint = data["checkpoint"]
    jsonschema.validate(instance=checkpoint, schema=schema)
    
    # Assert specific behavior for f10
    if fixture_name == "f10_insufficient_evidence":
        assert checkpoint["claim_boundary"] == "unknown"
        assert checkpoint["abstain_reason"] == "insufficient_input_evidence"
    else:
        assert checkpoint["claim_boundary"] == "observation_only"

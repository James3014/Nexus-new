
import json
import pytest
import jsonschema
from pathlib import Path
import subprocess

SCHEMA_PATH = Path("schemas/s2t_memory_sidecar_checkpoint.schema.json")

@pytest.fixture
def schema():
    with SCHEMA_PATH.open("r") as f:
        return json.load(f)

def test_checkpoint_schema_valid(schema):
    valid_obj = {
        "schema": "nexus.s2t_memory_sidecar_checkpoint.v1",
        "task_id": "test-001",
        "mode": "bootstrapping",
        "summary": "Everything is fine.",
        "completed_steps": ["step1"],
        "open_blockers": [],
        "evidence_refs": ["receipt.json"],
        "next_action": "commit",
        "claim_boundary": "verified",
        "confidence": "high"
    }
    jsonschema.validate(instance=valid_obj, schema=schema)

def test_checkpoint_schema_invalid_mode(schema):
    invalid_obj = {
        "schema": "nexus.s2t_memory_sidecar_checkpoint.v1",
        "task_id": "test-001",
        "mode": "wrong_mode",
        "summary": "Everything is fine.",
        "completed_steps": [],
        "open_blockers": [],
        "evidence_refs": [],
        "next_action": "wait",
        "claim_boundary": "unknown",
        "confidence": "low"
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_obj, schema=schema)

def test_checkpoint_schema_missing_required(schema):
    incomplete_obj = {
        "schema": "nexus.s2t_memory_sidecar_checkpoint.v1",
        "task_id": "test-001"
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=incomplete_obj, schema=schema)

def test_shadow_runner_output(tmp_path):
    output_file = tmp_path / "shadow.jsonl"
    log_file = tmp_path / "test.log"
    log_file.write_text("dummy log content")
    
    # Run shadow runner in mock mode
    cmd = [
        "python3", "scripts/bench/s2t_memory_sidecar_shadow.py",
        "--task-id", "runner-test-001",
        "--log", str(log_file),
        "--output", str(output_file),
        "--mock"
    ]
    subprocess.run(cmd, check=True)
    
    assert output_file.exists()
    with output_file.open("r") as f:
        line = f.readline()
        data = json.loads(line)
        
    assert data["task_id"] == "runner-test-001"
    checkpoint = data["checkpoint"]
    
    # Validate runner output against schema
    with SCHEMA_PATH.open("r") as f:
        schema_data = json.load(f)
    jsonschema.validate(instance=checkpoint, schema=schema_data)
    
    assert checkpoint["claim_boundary"] == "observation_only"
    assert checkpoint["mode"] == "bootstrapping"
    assert "input_hashes" in data
    assert data["input_hashes"]["log"] is not None

import pytest
import json
from pathlib import Path
from scripts.ops.learn_benchmark_rollup import rollup

def test_rollup_calculates_averages(tmp_path: Path):
    input_dir = tmp_path / "reports"
    input_dir.mkdir()
    (input_dir / "precision_1.json").write_text(json.dumps({"precision": 0.8, "unknown_correct_rate": 1.0}))
    (input_dir / "precision_2.json").write_text(json.dumps({"precision": 1.0, "unknown_correct_rate": 1.0}))
    
    output = tmp_path / "summary.json"
    rollup(str(input_dir), str(output))
    
    assert output.exists()
    data = json.loads(output.read_text())
    assert data["metrics"]["avg_precision"] == 0.9

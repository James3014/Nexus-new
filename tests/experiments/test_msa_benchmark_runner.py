import pytest
import os
import json
import tempfile
import sys
from unittest.mock import patch

from nexus.experiments.msa_routing.benchmark_runner import load_dataset, run_baseline, run_msa, main

def test_load_dataset_empty_fails():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        json.dump([], f)
        temp_path = f.name
    
    with pytest.raises(ValueError, match="Dataset is empty"):
        load_dataset(temp_path)
    
    os.remove(temp_path)

def test_benchmark_has_results():
    mock_data = [
        {"id": "1", "query": "test", "expected_mode": "ANSWERED", "expected_domain": "test"},
        {"id": "2", "query": "test2", "expected_mode": "UNKNOWN", "expected_domain": "test"}
    ]
    baseline_res = run_baseline(mock_data)
    assert "precision" in baseline_res
    assert "unknown_correct_rate" in baseline_res
    
    msa_res = run_msa(mock_data)
    assert "precision" in msa_res
    assert "unknown_correct_rate" in msa_res

def test_kill_switch_triggers_non_success():
    mock_data = [
        {"id": "1", "query": "test", "expected_mode": "ANSWERED", "expected_domain": "test"}
    ]
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as data_f:
        json.dump(mock_data, data_f)
        dataset_path = data_f.name
        
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as out_f:
        out_path = out_f.name

    # Mock evaluate_kill_switch to always raise error
    with patch("nexus.experiments.msa_routing.msa_lifecycle.MSALifecycle.evaluate_kill_switch") as mock_kill:
        from nexus.experiments.msa_routing.msa_lifecycle import KillSwitchTriggeredError
        mock_kill.side_effect = KillSwitchTriggeredError("Mock Triggered")
        
        test_args = ["benchmark_runner.py", "--dataset", dataset_path, "--out", out_path]
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit) as e:
                main()
            assert e.value.code == 1

    os.remove(dataset_path)
    os.remove(out_path)

def test_output_schema():
    mock_data = [
        {"id": "1", "query": "test", "expected_mode": "ANSWERED", "expected_domain": "test"}
    ]
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as data_f:
        json.dump(mock_data, data_f)
        dataset_path = data_f.name
        
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as out_f:
        out_path = out_f.name

    test_args = ["benchmark_runner.py", "--dataset", dataset_path, "--out", out_path]
    with patch.object(sys, 'argv', test_args):
        try:
            main()
        except SystemExit:
            pass

    with open(out_path, 'r') as f:
        res = json.load(f)
        
    assert "precision" in res
    assert "unknown_correct_rate" in res
    assert "regression_rate" in res
    assert "cost_per_success" in res
    assert "p50_latency_ms" in res
    assert "kill_switch_triggered" in res
    assert "kill_switch_reasons" in res
    assert "baseline" in res
    assert "msa" in res

    os.remove(dataset_path)
    os.remove(out_path)
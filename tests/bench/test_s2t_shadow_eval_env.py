import os
import ast
import pytest
from pathlib import Path
from unittest.mock import patch
from scripts.bench.s2t_shadow_eval import run_shadow_eval

def test_s2t_shadow_eval_signature_parity():
    """驗證 run_shadow_eval 函式簽名是否嚴格維持 10 個 positional/keyword 參數，防止 AST 審計漂移"""
    eval_file = Path(__file__).resolve().parents[2] / "scripts/bench/s2t_shadow_eval.py"
    code = eval_file.read_text(encoding="utf-8")
    tree = ast.parse(code)
    
    run_shadow_eval_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_shadow_eval":
            run_shadow_eval_node = node
            break
            
    assert run_shadow_eval_node is not None, "scripts/bench/s2t_shadow_eval.py 中必須定義 run_shadow_eval 函數"
    args = [arg.arg for arg in run_shadow_eval_node.args.args]
    
    # 確保只有這 10 個核心參數，且絕不包含 abstain_dataset_path
    expected_args = [
        "dataset_path", "output_report_path", "run_real", "device", 
        "timeout_sec", "offline", "emulator", "adapter_dir", 
        "use_ollama", "model_name"
    ]
    assert args == expected_args, f"函式簽名參數數目或順序不匹配！當前參數: {args}"

def test_s2t_shadow_eval_env_absent(tmp_path):
    """驗證當 NEXUS_ABSTAIN_DATASET_PATH 未設定 (absent) 時的行為正常"""
    dataset_file = tmp_path / "dataset.jsonl"
    dataset_file.write_text('{"task_id": "test-1", "input": {"candidate_summaries": []}, "target": {"selected_candidate_id": null}}\n')
    report_file = tmp_path / "report.json"
    
    with patch.dict(os.environ, {}):
        if "NEXUS_ABSTAIN_DATASET_PATH" in os.environ:
            del os.environ["NEXUS_ABSTAIN_DATASET_PATH"]
            
        # 執行 shadow eval 應該正常跑完而沒有加載 abstain_dataset
        res = run_shadow_eval(
            dataset_path=dataset_file,
            output_report_path=report_file,
            run_real=False,
            device="cpu",
            timeout_sec=5,
            offline=True,
            emulator=True
        )
        assert res is True
        assert report_file.exists()

def test_s2t_shadow_eval_env_malformed(tmp_path):
    """驗證當 NEXUS_ABSTAIN_DATASET_PATH 指向不存在的惡意/損毀檔案 (malformed) 時的容錯"""
    dataset_file = tmp_path / "dataset.jsonl"
    dataset_file.write_text('{"task_id": "test-1", "input": {"candidate_summaries": []}, "target": {"selected_candidate_id": null}}\n')
    report_file = tmp_path / "report.json"
    
    # 指向一個不存在的 path
    bad_path = str(tmp_path / "non_existent_file.jsonl")
    with patch.dict(os.environ, {"NEXUS_ABSTAIN_DATASET_PATH": bad_path}):
        # 執行 shadow eval 不應崩潰，應跳過加載 abstain 並正常完成
        res = run_shadow_eval(
            dataset_path=dataset_file,
            output_report_path=report_file,
            run_real=False,
            device="cpu",
            timeout_sec=5,
            offline=True,
            emulator=True
        )
        assert res is True
        assert report_file.exists()

def test_s2t_shadow_eval_cli_flag_sets_env(tmp_path):
    """驗證 CLI 參數 --abstain-dataset 是否會正確寫入 NEXUS_ABSTAIN_DATASET_PATH 環境變數"""
    import subprocess
    import sys
    
    dataset_file = tmp_path / "dataset.jsonl"
    dataset_file.write_text('{"task_id": "test-1", "input": {"candidate_summaries": []}, "target": {"selected_candidate_id": null}}\n')
    abstain_file = tmp_path / "abstain.jsonl"
    abstain_file.write_text('{"task_id": "abstain-1", "input": {"candidate_summaries": []}, "target": {"selected_candidate_id": null}}\n')
    report_file = tmp_path / "report.json"
    
    script_path = Path(__file__).resolve().parents[2] / "scripts/bench/s2t_shadow_eval.py"
    
    # 執行 CLI，驗證其是否正確解析並設定
    cmd = [
        sys.executable,
        str(script_path),
        "--dataset", str(dataset_file),
        "--abstain-dataset", str(abstain_file),
        "--output", str(report_file),
        "--emulator"
    ]
    
    # 使用 clean environment 執行，確保沒有預先存在的 env var 污染
    env = os.environ.copy()
    if "NEXUS_ABSTAIN_DATASET_PATH" in env:
        del env["NEXUS_ABSTAIN_DATASET_PATH"]
        
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 0, f"CLI 執行失敗: {result.stderr}\nStdout: {result.stdout}"
    
    # 檢查輸出日誌是否包含 loading abstention dataset，證明環境變數設定成功且被 run_shadow_eval 讀取
    assert "Loading abstention dataset" in result.stdout


from __future__ import annotations

import json
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock

from scripts.local_heal.run_ollama_local_solve_smoke import main


def test_smoke_runner_env_blocked() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with patch("sys.stdout") as mock_stdout:
            stdout_data = []
            mock_stdout.write = lambda s: stdout_data.append(s)
            
            with patch("sys.argv", ["run_ollama_local_solve_smoke.py"]):
                code = main()
                assert code == 0
                
            out = "".join(stdout_data)
            res = json.loads(out)
            assert res["model_called"] is False
            assert res["route_mode"] == "local_only_blocked"
            assert res["fallback_block_reason"] == "env_variables_disabled_for_real_ollama"


def test_smoke_runner_mocked_success() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "main.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")
            
        diff = """--- a/main.py
+++ b/main.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        # Ollama 格式通常為單一文本，有些也會回傳 choices / message，
        # 在 OllamaLocalModelProvider 中，其對 read() 的解法為:
        # payload = json.loads(response.read().decode("utf-8"))
        # response_text = payload.get("response", "")
        # 所以對 Ollama API 而言，回傳的欄位是 "response"！
        # 為了貼合 Ollama API 規格，我們將 Mock 欄位設定為 "response": f"```diff\n{diff}```"
        mock_response = {
            "response": f"```diff\n{diff}```"
        }
        
        mock_read = MagicMock(return_value=json.dumps(mock_response).encode("utf-8"))
        mock_conn = MagicMock()
        mock_conn.read = mock_read
        mock_conn.__enter__.return_value = mock_conn
        
        env = {
            "NEXUS_LOCAL_SOLVE_SMOKE_ENABLE": "1",
            "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
            "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
            "NEXUS_LOCAL_MODEL_NAME": "qwen2.5-coder",
        }
        
        with patch.dict(os.environ, env, clear=True):
            with patch("urllib.request.urlopen", return_value=mock_conn):
                with patch("sys.stdout") as mock_stdout:
                    stdout_data = []
                    mock_stdout.write = lambda s: stdout_data.append(s)
                    
                    argv = [
                        "run_ollama_local_solve_smoke.py",
                        "--source-root", src_root,
                        "--target-file", test_file,
                        "--verifier-command", "python3 -c 'print(1)'",
                        "--locked-search", "print('hello')\n",
                    ]
                    with patch("sys.argv", argv):
                        code = main()
                        assert code == 0
                        
                    out = "".join(stdout_data)
                    res = json.loads(out)
                    assert res["model_called"] is True
                    assert res["parser_status"] == "pass"
                    assert res["patch_apply_status"] == "applied"
                    assert res["verifier_status"] == "pass"
                    assert res["route_mode"] == "local_only_executed"
                    assert res["gate_passed"] is True
                    assert res["public_claim_allowed"] is False
                    assert res["production_ready"] is False
                    
        with open(src_path, "r", encoding="utf-8") as f:
            assert f.read() == "print('hello')\n"

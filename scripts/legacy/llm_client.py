"""
⚠️ LEGACY / ARCHIVED SCRIPT
This script is part of the legacy Muse-Nexus implementation and is no longer actively maintained.
Please use the corresponding module in `scripts/core/` or `nexus/` instead.
---
⚠️ 舊版 / 封存腳本
此腳本為舊版 Muse-Nexus 實作，已不再主動維護。
請改用 `scripts/core/` 或 `nexus/` 中的對應模組。
"""
import subprocess
import json
import fcntl
import shutil
import re


class LLMClient:
    """負責與 LLM (Codex) 的通訊與結果解析。"""

    def __init__(self, bin_path=None, lock_file=None):
        # 優先使用傳入路徑，否則動態偵測絕對路徑
        self.llm_bin = bin_path or shutil.which("codex") or "codex"
        self.lock_file = lock_file or "/tmp/codex_loop_v2.lock"

    def ask(self, prompt, payload):
        """執行 LLM 請求並返回解析後的 JSON 結果。"""
        full_prompt = prompt + payload
        try:
            with open(self.lock_file, "w") as lock_f:
                fcntl.flock(lock_f, fcntl.LOCK_EX)
                res = subprocess.run(
                    [self.llm_bin, "exec", "-"],
                    input=full_prompt,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )

            # 🛡️ 魯棒性 JSON 提取 (符合 Lvl 16 Lessons)
            output = res.stdout + res.stderr
            # 🛡️ 提前提取 Token 消耗 (Lvl 16 DX)
            tokens_total = 0
            token_match = re.search(r"tokens used\s+(\d+(?:,\d+)?)", output)
            if token_match:
                tokens_total = int(token_match.group(1).replace(",", ""))

            try:
                # 優先尋找最後一個 JSON 區塊，避免日誌干擾
                if "```json" in output:
                    json_blocks = output.split("```json")
                    json_str = json_blocks[-1].split("```")[0].strip()
                elif "{" in output:
                    # 選取最後一個可能的 JSON 對象
                    start_idx = output.rfind("{")
                    end_idx = output.rfind("}") + 1
                    if start_idx < end_idx:
                        json_str = output[start_idx:end_idx]
                    else:
                        json_str = output.strip()
                else:
                    json_str = output.strip()

                data = json.loads(json_str)
                data["tokens_used"] = tokens_total

                # 驗證 Schema 合規性
                if not isinstance(data, dict) or "status" not in data:
                    raise ValueError(f"Missing required 'status' field in {data}")

                return data, output
            except (json.JSONDecodeError, IndexError, ValueError) as e:
                # 🛡️ 失敗時輸出原始資訊以便微調
                print(f"⚠️ [JSON_PARSE_ERROR] {e}")
                print(f"--- RAW OUTPUT START ---\n{output}\n--- RAW OUTPUT END ---")
                return {
                    "status": "FAIL",
                    "summary": f"JSON parsing error: {e}",
                    "violations": [],
                    "tokens_used": tokens_total,
                }, output

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return {
                "status": "FAIL",
                "summary": f"LLM client error: {e}",
                "violations": [],
                "tokens_used": 0,
            }, str(e)

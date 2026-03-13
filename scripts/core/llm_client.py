import subprocess
import json
import fcntl
import shutil
import re
import tempfile
from pathlib import Path


class LLMClient:
    """負責與 LLM (Codex) 的通訊與結果解析。"""

    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "summary": {"type": "string"},
            "violations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "severity": {"type": "string"},
                        "type": {"type": "string"},
                        "reason": {"type": "string"},
                        "suggestion": {"type": "string"},
                        "patch": {"type": "string"},
                    },
                    "required": ["file", "reason", "suggestion"],
                },
            },
        },
        "required": ["status", "summary", "violations"],
    }

    def __init__(self, bin_path=None, lock_file=None):
        # 優先使用傳入路徑，否則動態偵測絕對路徑
        self.llm_bin = bin_path or shutil.which("codex") or "codex"
        self.lock_file = lock_file or "/tmp/codex_loop_v2.lock"

    def _build_error_result(self, summary, output="", tokens_total=0, category="llm_error"):
        return {
            "status": "FAIL",
            "summary": summary,
            "violations": [],
            "tokens_used": tokens_total,
            "error_category": category,
            "raw_excerpt": output[-800:] if output else "",
        }

    def _categorize_runtime_error(self, output):
        text = output.lower()
        if "failed to lookup address information" in text or "error sending request for url" in text:
            return "codex backend unreachable (dns/network failure)", "backend_unreachable"
        if "could not create otel exporter" in text or "opentelemetry" in text:
            return "codex telemetry startup failure", "telemetry_failure"
        if "mcp startup" in text and "failed:" in text:
            return "codex mcp startup failure", "mcp_startup_failure"
        if "panicked at" in text or "thread 'main' panicked" in text:
            return "codex cli runtime panic", "cli_panic"
        return "", ""

    def _build_codex_command(self, schema_path):
        return [
            self.llm_bin,
            "exec",
            "-",
            "--color",
            "never",
            "--output-schema",
            str(schema_path),
        ]

    def ask(self, prompt, payload):
        """執行 LLM 請求並返回解析後的 JSON 結果。"""
        full_prompt = prompt + payload
        schema_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(self.OUTPUT_SCHEMA, tmp, ensure_ascii=False)
                schema_file = Path(tmp.name)

            with open(self.lock_file, "w") as lock_f:
                fcntl.flock(lock_f, fcntl.LOCK_EX)
                res = subprocess.run(
                    self._build_codex_command(schema_file),
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

            runtime_summary, category = self._categorize_runtime_error(output)
            if runtime_summary:
                return self._build_error_result(
                    runtime_summary, output=output, tokens_total=tokens_total, category=category
                ), output

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
                return self._build_error_result(
                    f"codex returned non-schema output: {e}",
                    output=output,
                    tokens_total=tokens_total,
                    category="invalid_model_output",
                ), output

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return self._build_error_result(
                f"LLM client error: {e}",
                output=str(e),
                tokens_total=0,
                category="client_invocation_error",
            ), str(e)
        finally:
            if schema_file and schema_file.exists():
                schema_file.unlink(missing_ok=True)

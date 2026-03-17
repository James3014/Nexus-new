import subprocess
import json
import fcntl
import shutil
import re
import tempfile
from pathlib import Path
from typing import Any


class LLMClient:
    """負責與 LLM (Codex) 的通訊與結果解析，並具備 v7 領域適應能力。"""

    def __init__(self, bin_path=None, lock_file=None, project_root=None):
        # 優先使用傳入路徑，否則動態偵測絕對路徑
        self.llm_bin = (
            bin_path
            or "/Users/jameschen/.npm-global/bin/codex"
            or shutil.which("codex")
            or shutil.which("codex-loop")
            or "/Users/jameschen/.local/bin/codex-loop"
        )
        self.lock_file = lock_file or "/tmp/codex_loop_v2.lock"
        self.project_root = Path(project_root or ".")

        from nexus.services.prompt_builder import PromptBuilder

        self.prompt_builder = PromptBuilder(str(self.project_root))

    def get_anti_token_estimate(self) -> int:
        """
        🛡️ Anti-Self-Metering: 估計指揮官（本體）的消耗量。
        目前透過掃描 .nexus 目錄實作。
        """
        try:
            # 簡化算法：掃描當前對話歷史
            log_folder = self.project_root / ".nexus" / "transcripts"
            total = 0
            for f in log_folder.glob("*.md"):
                total += len(f.read_text()) // 4  # 約略估計
            return total
        except:
            return 0

    OUTPUT_SCHEMA = {
        "status": "APPROVED | REJECTED | FAIL",
        "summary": "Short explanation",
        "violations": ["list of rule violations"],
    }

    def _build_error_result(
        self,
        summary,
        output="",
        tokens_total=0,
        token_raw_model=0,
        token_fallback_est=0,
        capture_status="unknown",
        category="llm_error",
    ):
        return {
            "status": "FAIL",
            "summary": summary,
            "violations": [],
            "tokens_used": tokens_total,
            "token_raw_model": token_raw_model,
            "token_fallback_est": token_fallback_est,
            "token_capture_status": capture_status,
            "error_category": category,
            "raw_excerpt": output[-800:] if output else "",
        }

    def _categorize_runtime_error(self, output):
        text = output.lower()
        if (
            "failed to lookup address information" in text
            or "error sending request for url" in text
        ):
            return (
                "codex backend unreachable (dns/network failure)",
                "backend_unreachable",
            )
        if "could not create otel exporter" in text or "opentelemetry" in text:
            return "codex telemetry startup failure", "telemetry_failure"
        if "mcp startup" in text and "failed:" in text:
            return "codex mcp startup failure", "mcp_startup_failure"
        if "panicked at" in text or "thread 'main' panicked" in text:
            return "codex cli runtime panic", "cli_panic"
        return "", ""

    def ask_with_template(
        self, task: str, diff: str, model_hint: str = "flash", phase: str = "R"
    ) -> tuple[Any, str]:
        """使用 PromptBuilder 組合完整 Payload 並發送請求。"""
        full_payload = self.prompt_builder.build_full_payload(
            phase, task, diff, model_hint
        )
        return self.ask(full_payload, "", phase=phase)

    def model_selector(self, phase: str, domain: str = "general") -> str:
        """
        🎡 Nexus Wheel-Shift: 動態模型選擇器 (Lvl 19)
        - P/X (Plan/Research): 優先使用 Claude (邏輯縝密)
        - R/A (Repair/Audit): 優先使用 Gemini (審查精準)
        """
        mapping = {
            "P": "claude-3.5-sonnet",
            "D": "claude-3.5-sonnet",
            "X": "claude-3.5-sonnet",
            "R": "claude-3.5-sonnet",
            "A": "claude-3.5-sonnet",
            "C": "claude-3.5-sonnet",
        }
        target_model = mapping.get(phase, "claude-3.5-sonnet")
        print(f"🎡 [Wheel-Shift] Phase {phase} -> Model: {target_model}")
        return target_model

    def _build_codex_command(self, schema_path, model_name=None):
        cmd = [self.llm_bin]

        # 🛡️ v1.8 魯棒性: 若使用的是 codex-loop 腳本，則改用相容參數
        is_brain_script = "codex-loop" in str(self.llm_bin)

        if is_brain_script:
            # codex-loop 腳本模式不支援 exec 與 output-schema
            # 這裡我們模擬一個可以直接接受 input 的模式，或報錯提示
            print(
                "⚠️ [Compatibility] Using codex-loop script wrapper. Flags may differ."
            )
            cmd.extend(["--mode", "developer", "--apply"])
        else:
            cmd.extend(
                [
                    "exec",
                    "-",
                    "--color",
                    "never",
                    "--output-schema",
                    str(schema_path),
                ]
            )
            if model_name:
                cmd.extend(["--model", model_name])
        return cmd

    def ask(self, prompt, payload, phase="P", second_opinion=False):
        """執行 LLM 請求。"""
        model_name = self.model_selector(phase)
        full_prompt = prompt + payload  # 此時 prompt 已由 Builder 處理
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
                    self._build_codex_command(schema_file, model_name),
                    input=full_prompt,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )

            # 🛡️ 魯棒性 JSON 提取 (符合 Lvl 16 Lessons)
            output = res.stdout + res.stderr
            # 🛡️ 提前提取 Token 消耗
            tokens_total = 0
            capture_status = "not_triggered"

            import os

            debug_enabled = os.getenv("NEXUS_DEBUG_TOKENS") == "1"

            # 格式 1: tokens used 123
            token_match = re.search(r"tokens used\s+(\d+(?:,\d+)?)", output, re.I)
            # 格式 2: [Metrics] total_tokens: 123
            token_match_v2 = re.search(
                r"total_tokens[:\s]+(\d+(?:,\d+)?)", output, re.I
            )
            # 格式 3: usage: { ..."total_tokens": 123 }
            token_match_v3 = re.search(r"\"total_tokens\":\s*(\d+)", output, re.I)
            # 格式 4: Total Session Tokens: 1,234
            token_match_v4 = re.search(
                r"Total Session Tokens:\s*(\d+(?:,\d+)?)", output, re.I
            )

            match = token_match or token_match_v2 or token_match_v3 or token_match_v4
            if match:
                try:
                    tokens_total = int(match.group(1).replace(",", ""))
                    capture_status = "ok"
                except Exception:
                    capture_status = "parse_fail"
            elif output.strip():
                capture_status = "missing_usage"
            
            # 🛡️ VAR-102: Token 最終擷取門檻 (保底至少 10 以利審計)
            if tokens_total == 0 and output.strip():
                tokens_total = max(10, len(output) // 4)
                capture_status = "fallback_est"

            if debug_enabled:
                print(
                    f"🔍 [Token-Debug] Capture Status: {capture_status} | Tokens: {tokens_total}"
                )
                if capture_status != "ok":
                    snippet = output[:200].replace("\n", "\\n")
                    print(f"🔍 [Token-Debug] Raw Snippet: {snippet}...")

            runtime_summary, category = self._categorize_runtime_error(output)
            if runtime_summary:
                return self._build_error_result(
                    runtime_summary,
                    output=output,
                    tokens_total=tokens_total,
                    token_raw_model=tokens_total if capture_status == "ok" else 0,
                    token_fallback_est=tokens_total if capture_status == "fallback_est" else 0,
                    capture_status=capture_status,
                    category=category,
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
                data["token_raw_model"] = tokens_total if capture_status == "ok" else 0
                data["token_fallback_est"] = tokens_total if capture_status == "fallback_est" else 0
                data["token_capture_status"] = capture_status

                # 驗證 Schema 合規性
                if not isinstance(data, dict) or "status" not in data:
                    raise ValueError(f"Missing required 'status' field in {data}")

                return data, output
            except (json.JSONDecodeError, IndexError, ValueError) as e:
                # 🛡️ 失敗時輸出原始資訊以便微調
                print(f"⚠️ [JSON_PARSE_ERROR] {e}")
                print(f"--- RAW OUTPUT START ---\n{output}\n--- RAW OUTPUT END ---")
                err_res = self._build_error_result(
                    f"codex returned non-schema output: {e}",
                    output=output,
                    tokens_total=tokens_total,
                    token_raw_model=tokens_total if capture_status == "ok" else 0,
                    token_fallback_est=tokens_total if capture_status == "fallback_est" else 0,
                    capture_status=capture_status,
                    category="invalid_model_output",
                )
                err_res["token_raw_model"] = tokens_total if capture_status == "ok" else 0
                err_res["token_fallback_est"] = tokens_total if capture_status == "fallback_est" else 0
                err_res["token_capture_status"] = capture_status
                return err_res, output

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return self._build_error_result(
                f"LLM client error: {e}",
                output=str(e),
                tokens_total=0,
                token_raw_model=0,
                token_fallback_est=0,
                capture_status="not_triggered",
                category="client_invocation_error",
            ), str(e)
        finally:
            if schema_file and schema_file.exists():
                schema_file.unlink(missing_ok=True)

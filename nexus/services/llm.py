import subprocess
import json
import fcntl
import shutil
import re
import tempfile
import fcntl
from pathlib import Path
from typing import Any
import openai
from openai import OpenAI


class LLMClient:
    """負責與 LLM (Codex) 的通訊與結果解析，並具備 v7 領域適應能力。"""

    def __init__(self, bin_path=None, lock_file=None, project_root=None):
        # 優先使用傳入路徑，否則初始化 OpenAI 存取項
        self.client = OpenAI() # 這裡預期環境變數已具備配置
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

    # [REMOVED] _build_codex_command as we now use SDK directly

    def ask(self, prompt, payload, phase="P", second_opinion=False):
        """執行 LLM 請求 (Native SDK 版)。"""
        model_name = self.model_selector(phase)
        full_prompt = prompt + payload
        
        try:
            # 🛡️ v9 Hardened: 使用 SDK 直接請求以獲取精準 Token
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": f"You are a Nexus v9 agent. Return JSON matching this schema: {json.dumps(self.OUTPUT_SCHEMA)}"},
                    {"role": "user", "content": full_prompt}
                ],
                response_format={"type": "json_object"},
                timeout=180
            )
            
            output = response.choices[0].message.content or "{}"
            usage = response.usage
            
            tokens_total = usage.total_tokens
            capture_status = "ok"
            
            # 解析 JSON
            try:
                data = json.loads(output)
                data["tokens_used"] = tokens_total
                data["token_raw_model"] = tokens_total
                data["token_fallback_est"] = 0
                data["token_capture_status"] = capture_status
                
                # 驗證 Schema
                if not isinstance(data, dict) or "status" not in data:
                    # 如果模型沒給 status，補一個默認值避免 crash
                    data["status"] = "FAIL"
                    data["summary"] = data.get("summary") or "Model failed to provide descriptive status."
                
                return data, output
                
            except json.JSONDecodeError as e:
                print(f"⚠️ [JSON_PARSE_ERROR] {e}")
                return self._build_error_result(
                    f"LLM returned invalid JSON: {e}",
                    output=output,
                    tokens_total=tokens_total,
                    token_raw_model=tokens_total,
                    capture_status="ok",
                    category="invalid_json"
                ), output

        except Exception as e:
            # 🛡️ 捕捉 SDK 錯誤 (Timeout, API Error, etc.)
            print(f"❌ [LLM_SDK_ERROR] {e}")
            return self._build_error_result(
                f"LLM SDK error: {e}",
                output=str(e),
                tokens_total=0,
                capture_status="client_error",
                category="sdk_error"
            ), str(e)

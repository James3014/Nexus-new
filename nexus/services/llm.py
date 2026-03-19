import subprocess
import json
import fcntl
import shutil
import re
import tempfile
import os
from pathlib import Path
from typing import Any
try:
    from nexus.engine.phases.base import BasePhaseHandler
except ImportError:
    # Fallback if circular import
    class BasePhaseHandler:
        def __init__(self, *args, **kwargs): pass

try:
    from nexus.core.state_contracts import NexusState
except ImportError:
    NexusState = Any
    try:
        import openai
        from openai import OpenAI
    except ImportError:
        openai = None
        OpenAI = None


class LLMClient:
    """負責與 LLM (Codex) 的通訊與結果解析，並具備 v7 領域適應能力。"""

    def __init__(self, bin_path=None, lock_file=None, project_root=None):
        self.lock_file = lock_file or "/tmp/codex_loop_v2.lock"
        self.project_root = Path(project_root or ".")
        
        # 🛡️ v9 Auth Fallback: 支援 OPENAI_API_KEY 與 OAuth CLI 雙相容
        self.api_key = os.getenv("OPENAI_API_KEY")
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
            self.use_oauth = False
        else:
            self.client = None
            self.use_oauth = True
            self.oauth_provider = os.getenv("NEXUS_OAUTH_PROVIDER", "gemini")
            print(f"⚠️ [Auth] OPENAI_API_KEY missing. Falling back to OAuth CLI: {self.oauth_provider}")

        try:
            from nexus.services.prompt_builder import PromptBuilder
            self.prompt_builder = PromptBuilder(str(self.project_root))
        except (ImportError, TypeError):
            self.prompt_builder = None # type: ignore
            print("⚠️ [LLM] PromptBuilder loading failed.")

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
        # 如果是 OAuth 模式，強制映射到 provider 支援的模型
        if self.use_oauth:
            return "gemini-3-flash-preview" if phase in ["R", "A"] else "gemini-2.5-flash-lite"

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

    def ask(self, prompt, payload, phase="P", second_opinion=False):
        """執行 LLM 請求 (支援 Native SDK 與 OAuth CLI 雙路徑)。"""
        model_name = self.model_selector(phase)
        full_prompt = prompt + payload
        
        if self.use_oauth:
            return self._ask_via_cli(full_prompt, model_name, phase)
            
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
            
            return self._parse_json_response(output, tokens_total, capture_status)

        except Exception as e:
            print(f"❌ [LLM_SDK_ERROR] {e}")
            return self._build_error_result(
                f"LLM SDK error: {e}",
                output=str(e),
                tokens_total=0,
                capture_status="client_error",
                category="sdk_error"
            ), str(e)

    def _ask_via_cli(self, prompt, model_name, phase):
        """🛡️ OAuth Fallback: 透過 CLI (gemini) 獲取結果與真實 Token。"""
        import time
        max_retries = 3
        last_err = ""
        
        for attempt in range(max_retries):
            try:
                # 注入系統提示
                sys_msg = f"You are a Nexus v9 agent. Return JSON matching this schema: {json.dumps(self.OUTPUT_SCHEMA)}"
                
                # 實際執行時將 prompt 內容以 STDIN 方式傳入避免 ARG_MAX (PHA-021)
                res = subprocess.run(
                    [self.oauth_provider, "-p", sys_msg, "--output-format", "json"],
                    input=prompt,
                    capture_output=True, text=True, timeout=180
                )
                
                if res.returncode != 0:
                    last_err = res.stderr
                    print(f"⚠️ [LLM_CLI] Attempt {attempt+1} failed: {res.stderr}")
                    time.sleep(2 ** attempt) # Exponential backoff
                    continue
                    
                # 🛡️ Hardened: 由於 STDOUT 可能包含 "Loaded cached..." 等噪音，需提取純 JSON 部分
                stdout_str = str(res.stdout)
                json_start = stdout_str.find("{")
                json_end = stdout_str.rfind("}")
                if json_start == -1 or json_end == -1:
                    last_err = "No JSON in output"
                    print(f"⚠️ [LLM_CLI] Attempt {attempt+1} - No JSON found in output.")
                    continue
                    
                json_text = stdout_str[json_start : json_end + 1]
                data = json.loads(json_text)
                output = data.get("response", "{}")
                
                # 擷取真實 Token
                tokens_total = 0
                stats = data.get("stats", {}).get("models", {})
                if isinstance(stats, dict):
                    for m_stats in stats.values():
                        if isinstance(m_stats, dict):
                            tokens_total += m_stats.get("tokens", {}).get("total", 0)
                    
                return self._parse_json_response(output, tokens_total, "ok" if tokens_total > 0 else "fallback_est")
                
            except Exception as e:
                last_err = str(e)
                print(f"⚠️ [LLM_CLI] Attempt {attempt+1} exception: {e}")
                time.sleep(2 ** attempt)
                
        return self._build_error_result(
            f"CLI execution failed after {max_retries} retries: {last_err}", 
            capture_status="cli_error",
            category="cli_fallback_failure"
        ), last_err

    def _parse_json_response(self, output, tokens_total, capture_status):
        """統一解析 JSON 並注入 Token 指標。"""
        try:
            # 處理可能夾帶在 markdown block 中的 JSON
            clean_output = output
            if "```json" in output:
                match = re.search(r"```json\s*(.*?)\s*```", output, re.DOTALL)
                if match: clean_output = match.group(1)
            
            data = json.loads(clean_output)
            data["tokens_used"] = tokens_total
            data["token_raw_model"] = tokens_total
            data["token_fallback_est"] = 0 if capture_status == "ok" else tokens_total
            data["token_capture_status"] = capture_status
            
            if "status" not in data:
                data["status"] = "FAIL"
                data["summary"] = "Model failed to provide status."
                
            return data, output
            
        except json.JSONDecodeError as e:
            print(f"⚠️ [JSON_PARSE_ERROR] {e}")
            return self._build_error_result(
                f"Invalid JSON from LLM: {e}",
                output=output,
                tokens_total=tokens_total,
                token_raw_model=tokens_total,
                capture_status=capture_status,
                category="invalid_json"
            ), output


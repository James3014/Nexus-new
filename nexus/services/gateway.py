import subprocess
import json
import logging
import fcntl
import shutil
import re
import tempfile
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 🛡️ Nexus v16 Battlesuit Gateway (De-LLM-ized Edition)
# This module is strictly PASSIVE. It handles physical handoffs to the agent.

try:
    from nexus.engine.phases.base import BasePhaseHandler
except ImportError:
    class BasePhaseHandler:
        def __init__(self, *args, **kwargs): pass

try:
    from nexus.core.state_contracts import NexusState
except ImportError:
    NexusState = Any


class BattlesuitGateway:
    """
    🛡️ Nexus Battlesuit Gateway (物理戰甲閘道)
    取代原有的 LLMClient。不具備主動推理能力，僅負責「物理交接 (Handoff)」。
    """

    def __init__(self, bin_path=None, lock_file=None, project_root=None):
        self.lock_file = lock_file or os.getenv("NEXUS_LOCK_FILE", "/tmp/nexus_battlesuit.lock")
        self.project_root = Path(project_root or ".")
        
        # 🛡️ Battlesuit Origin: 僅支援 OAuth CLI 與物理 Handoff
        self.use_oauth = True
        self.oauth_provider = os.getenv("NEXUS_OAUTH_PROVIDER", "gemini")
        # 🛡️ Compatibility for legacy scripts
        self.llm_bin = self.oauth_provider
        
        # ❌ OPENAI SDK REMOVED (De-LLM-ized)
        self.client = None

        try:
            from nexus.services.prompt_builder import PromptBuilder
            self.prompt_builder = PromptBuilder(str(self.project_root))
        except (ImportError, TypeError):
            self.prompt_builder = None # type: ignore

    def get_anti_token_estimate(self) -> int:
        """估計戰甲外部消耗量。"""
        try:
            log_folder = self.project_root / ".nexus" / "transcripts"
            total = 0
            for f in log_folder.glob("*.md"):
                total += len(f.read_text()) // 4
            return total
        except Exception as e:
            logger.debug("Token estimation failed: %s", e)
            return 0

    OUTPUT_SCHEMA = {
        "status": "APPROVED | REJECTED | FAIL",
        "summary": "Short explanation",
        "violations": ["list of rule violations"],
    }

    def _build_error_result(self, summary, category="gateway_error"):
        return {
            "status": "FAIL",
            "summary": summary,
            "violations": [],
            "tokens_used": 0,
            "error_category": category,
        }

    def ask_with_template(
        self, task: str, diff: str, model_hint: str = "flash", phase: str = "R"
    ) -> tuple[Any, str]:
        """產出交接 Payload。"""
        if self.prompt_builder:
            full_payload = self.prompt_builder.build_full_payload(
                phase, task, diff, model_hint
            )
            return self.ask(full_payload, "", phase=phase)
        return self.ask(task, diff, phase=phase)

    def model_selector(self, phase: str) -> str:
        """被動映射模型名稱。"""
        return "gemini-3-flash-preview" if phase in ["R", "A"] else "gemini-2.5-flash-lite"

    def ask(self, prompt, payload, phase="P", second_opinion=False):
        """
        執行物理交接 (Handoff)。
        Nexus 作為戰甲，將請求轉發給外部 CLI 或產出 Handoff 文件。
        """
        model_name = self.model_selector(phase)
        full_content = f"{prompt}\n\n[PAYLOAD/DIFF]\n{payload}"
        
        # 🛡️ 核心邏輯：僅允許透過 CLI 路徑進行通訊
        return self._ask_via_cli(full_content, model_name, phase)

    def _ask_via_cli(self, content, model_name, phase):
        """🛡️ Battlesuit Forwarding: 透過外部實體工具獲取認知判斷。"""
        import time
        max_retries = 3
        last_err = ""
        
        sys_msg = (
            "You are the pilot of the Nexus Battlesuit v16. "
            f"Return ONLY valid JSON matching: {json.dumps(self.OUTPUT_SCHEMA)}"
        )

        for attempt in range(max_retries):
            try:
                # 🛡️ Nexus Integration: 使用 --output-format json 確保物理純淨度
                cmd = [self.oauth_provider, "-m", model_name, "-p", sys_msg]
                cmd.extend(["--output-format", "json"])
                
                res = subprocess.run(
                    cmd,
                    input=content,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=180
                )
                
                if res.returncode != 0:
                    last_err = res.stderr or res.stdout
                    time.sleep(2 ** attempt)
                    continue
                
                raw_stdout = res.stdout.strip()
                try:
                    # gemini CLI output is usually { "output": "..." } when using --output-format json
                    # but it depends on the version. Let's be robust.
                    resp_json = json.loads(raw_stdout)
                    
                    # 提取主要輸出
                    output_text = resp_json.get("output", raw_stdout)
                    
                    # 提取 Token 資訊 (從 gemini CLI 的 JSON 結構中)
                    tokens_total = 0
                    stats = resp_json.get("stats", {}).get("models", {})
                    if isinstance(stats, dict):
                        for m_stats in stats.values():
                            if isinstance(m_stats, dict):
                                tokens_total += m_stats.get("tokens", {}).get("total", 0)
                                
                    return self._parse_json_result(output_text, tokens_total, "ok")
                    
                except json.JSONDecodeError:
                    # 如果不是 JSON，回退到正則提取
                    return self._parse_json_result(raw_stdout, 0, "fallback_regex")
                    
            except Exception as e:
                last_err = str(e)
                time.sleep(2 ** attempt)
                
        return self._build_error_result(
            f"Battlesuit Forwarding failed: {last_err}", 
            category="cli_failure"
        ), last_err

    def _parse_json_result(self, raw_text, tokens_total, capture_status):
        """解析模型產出的 JSON 內容。"""
        try:
            # 1. 嘗試直接解析
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                # 2. 嘗試正則提取
                match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1).strip())
                else:
                    # 3. 嘗試提取第一個 { 到最後一個 }
                    start = raw_text.find("{")
                    end = raw_text.rfind("}")
                    if start != -1 and end != -1:
                        data = json.loads(raw_text[start:end+1])
                    else:
                        raise ValueError("No JSON block found")

            # 補完標準欄位
            data.setdefault("status", "FAIL")
            data.setdefault("summary", "No summary provided")
            data.setdefault("violations", [])
            data["tokens_used"] = tokens_total
            data["token_capture_status"] = capture_status
            
            return data, raw_text
            
        except Exception as e:
            return self._build_error_result(f"Parse Error: {str(e)}", category="parse_failure"), raw_text

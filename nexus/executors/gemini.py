import subprocess
import re
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from .base import BaseExecutor
from .protocol import (
    ExecutorInput, 
    ExecutorOutput, 
    ExecutorStatusEnum, 
    ProviderErrorType,
    ExecutionEvidence,
    ExecutorMeta,
    WorkspaceMeta
)

class GeminiExecutor(BaseExecutor):
    """
    ♊ GeminiExecutor
    第一個符合 MG-P0+ 協議的實體適配器。
    核心職責：消磁、隔離、標記提取、錯誤歸一化。
    """
    
    def __init__(self, model_name: str = "gemini-3-flash-preview"):
        self.model_name = model_name
        self.gemini_bin = shutil.which("gemini") or "gemini"
        # 物理隔離目錄
        self.sandbox_dir = Path("/Users/jameschen/Downloads/nexus_sandbox")
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        
    def execute(self, input_data: ExecutorInput, timeout: int = 240) -> ExecutorOutput:
        """實作協議入口：Input -> [Demagnetize -> Invoke -> Extract -> Classify] -> Output"""
        
        # 1. 語義消磁 + Prompt 組合
        full_prompt = self._build_protocol_prompt(input_data)
        
        # 2. 物理隔離執行
        try:
            res = subprocess.run(
                [
                    self.gemini_bin, 
                    "-m", self.model_name, 
                    "-y", 
                    "--telemetry-outfile", "/dev/null",
                    "--include-directories", str(self.sandbox_dir),
                    "--include-directories", str(input_data.workspace_root)
                ],
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=timeout, # P0: 基準測試逾時保護
                cwd=str(self.sandbox_dir)
            )
            stdout, stderr = res.stdout, res.stderr
            exit_code = res.returncode
        except subprocess.TimeoutExpired:
            print(f"🚨 [benchmark_timeout_guard] Execution timed out after {timeout}s.")
            return self._build_error_output(input_data.phase, f"EXECUTOR_TIMEOUT after {timeout}s", ProviderErrorType.EXECUTOR_TIMEOUT)
        except Exception as e:
            return self._build_error_output(input_data.phase, str(e), ProviderErrorType.UNKNOWN_PROVIDER_ERROR)

        # 3. Marker 提取與解析
        raw_combined = stdout + stderr
        
        # [DEBUG] 寫入除錯紀錄
        try:
            Path("/tmp/gemini_debug_prompt.txt").write_text(full_prompt, encoding="utf-8")
            Path("/tmp/gemini_debug_output.txt").write_text(raw_combined, encoding="utf-8")
        except Exception:
            pass
            
        parsed_data, parse_error = self._extract_marker_payload(raw_combined)
        
        # 4. 錯誤歸一化 (Normalization)
        if parse_error:
            # 偵測是否為特定的 Provider 錯誤（Quota, Interference 等）
            error_type = self._classify_provider_error(raw_combined, exit_code)
            return self._build_error_output(
                input_data.phase, 
                f"Parse Error: {parse_error}", 
                error_type,
                raw_output=raw_combined,
                exit_code=exit_code
            )

        # 5. 封裝標準輸出
        status = ExecutorStatusEnum.SUCCESS if parsed_data.get("status") == "PASS" else ExecutorStatusEnum.NO_PATCH
        if parsed_data.get("status") == "FAIL":
            status = ExecutorStatusEnum.EXECUTION_FAIL
            
        return ExecutorOutput(
            executor_name="gemini_adapter_v1",
            phase=input_data.phase,
            status=status,
            patch_generated=parsed_data.get("patch_generated", False),
            evidence_present=True,
            raw_exit_code=exit_code,
            files_touched=parsed_data.get("files_touched", []),
            summary=parsed_data.get("summary", "Execution completed via protocol."),
            patch_diff=parsed_data.get("patch"),
            diagnosis=parsed_data.get("diagnosis"),
            meta={
                "model_name": self.model_name,
                "tokens_output": parsed_data.get("tokens_used", 0)
            }
        )

    def _build_protocol_prompt(self, data: ExecutorInput) -> str:
        """實施「語義消磁」與「Marker 注入」。"""
        protocol_wrapper = (
            "\n\n--- [NEXUS_PROTOCOL_ACTIVE] ---\n"
            "SERVER_MODE: PASSIVE_LOGIC_ENGINE\n"
            "RESTRICTIONS: [NO_FILE_ACCESS, NO_TOOL_EXECUTION]\n"
            "DIRECTIVES: [TOOLS_DISABLED, ALL_INPUTS_INLINE, RETURN_SINGLE_JSON_PACKET_ONLY]\n"
            "ASSERTION: You are a passive transformation engine. All context is provided below. "
            "DO NOT attempt to read external files. DO NOT use internal shell tools or perform tool execution. "
            "Output MUST be a single valid JSON block wrapped in markers. "
            "CRITICAL: If you do not include <NEXUS_JSON_BEGIN> and <NEXUS_JSON_END>, the transaction will fail.\n"
            "FORMAT: <NEXUS_JSON_BEGIN>\n{...}\n<NEXUS_JSON_END>\n"
            "-----------------------------------\n"
        )

        
        # 消磁映射 (強化版：隱藏關鍵字以降低工具啟發機率)
        magnet_map = {
            "read_file": "TRANSFORM_BLOB",
            "write_file": "EMIT_PATCH",
            "run_command": "VIRTUAL_EXECUTE"
        }
        
        # 組合上下文與路徑抽象化 (Path Abstraction)
        self._path_mapping = {}
        ctx = ""
        for i, (path, content) in enumerate(data.context_pack.files.items()):
            alias = f"[FILE_{i+1}]"
            self._path_mapping[alias] = path
            ctx += f"\nFILE_ENTITY: {alias}\nCONTENT:\n{content}\n"
            
        prompt = f"{protocol_wrapper}\nTASK: {data.instruction.objective if data.instruction else 'Repair the code'}\n"
        
        # 💎 [Lvl 18.2] 鐵律注入 (Steel Rules Injection)
        if data.rules:
            prompt += "\nSTEEL_RULES_FROM_KNOWLEDGE_BASE:\n"
            for rule in data.rules:
                prompt += f"- {rule}\n"
            prompt += "\n"

        prompt += f"CONTEXT:\n{ctx}\n"
        
        # Linter Errors 路徑同步抽象化
        linter_str = json.dumps(data.context_pack.linter_errors)
        for alias, real_path in self._path_mapping.items():
            linter_str = linter_str.replace(real_path, alias)
        prompt += f"LINTER_ERRORS:\n{linter_str}\n"
        
        # 最後的消磁處理
        for old, new in magnet_map.items():
            prompt = prompt.replace(old, new)
            
        return prompt

    def _extract_marker_payload(self, output: str) -> tuple[Optional[dict], Optional[str]]:
        """Marker 協議提取器。"""
        # 🛡️ Resilience: 偵測輸出是否被截斷 (Truncation)
        if len(output) > 100 * 1024:
             # 如果輸出巨大且沒有結尾標籤，極大機率已截斷
             if "<NEXUS_JSON_BEGIN>" in output and "<NEXUS_JSON_END>" not in output:
                  return None, "OUTPUT_TRUNCATED: Response exceeded character limit or was cut off."

        marker_match = re.search(r'<NEXUS_JSON_BEGIN>(.*?)<NEXUS_JSON_END>', output, re.DOTALL)
        if not marker_match:
            # P2: 分類遺失標記為 PROVIDER_CONTRACT_VIOLATION
            return None, "PROVIDER_CONTRACT_VIOLATION: Missing <NEXUS_JSON_BEGIN> markers."
            
        payload = marker_match.group(1).strip()
        
        # 雙向還原：在 JSON 解碼前，將 [FILE_n] 換回真實絕對路徑
        if hasattr(self, "_path_mapping"):
            for alias, real_path in self._path_mapping.items():
                payload = payload.replace(alias, real_path)
                
        try:
            return json.loads(payload), None
        except json.JSONDecodeError as e:
            return None, f"JSON Decode Error: {str(e)}"

    def _classify_provider_error(self, output: str, error: object) -> ProviderErrorType:
        """Provider 錯誤歸一化分類器。接受 output 文字與 error (可為 Exception 或 exit_code int)。"""
        # 合併所有可用文字進行分析
        error_str = str(error).lower() if error is not None else ""
        text = (output + " " + error_str).lower()

        if "executor_timeout" in text:
            return ProviderErrorType.EXECUTOR_TIMEOUT
        if "429" in text or "usage limit" in text or "resource_exhausted" in text or "quota exceeded" in text or "quota_limit" in text:
            return ProviderErrorType.QUOTA_LIMIT
        if "provider_contract_violation" in text or "missing <nexus_json_begin>" in text:
            return ProviderErrorType.PROVIDER_CONTRACT_VIOLATION
        if "output_truncated" in text:
            return ProviderErrorType.OUTPUT_TRUNCATED
        if any(x in text for x in ["tool_use", "error executing tool", "read_file", "write_file", "file path must be within"]):
            return ProviderErrorType.AGENT_TOOL_INTERFERENCE
        if "permission denied" in text or "sandbox" in text:
            return ProviderErrorType.SANDBOX_PERMISSION_ERROR
        if isinstance(error, int) and error != 0:
            return ProviderErrorType.EXECUTOR_RUNTIME_ERROR
        if isinstance(error, Exception):
            return ProviderErrorType.EXECUTOR_RUNTIME_ERROR
        return ProviderErrorType.SCHEMA_VIOLATION

    def _build_error_output(self, phase, message, error_type, raw_output="", exit_code=1) -> ExecutorOutput:
        return ExecutorOutput(
            executor_name="gemini_adapter_v1",
            phase=phase,
            status=ExecutorStatusEnum.PROVIDER_ERROR,
            patch_generated=False,
            evidence_present=False,
            raw_exit_code=exit_code,
            summary=f"Provider Error: {message}",
            provider_error_type=error_type,
            stderr_excerpt=raw_output[-1000:]
        )

import re
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from .base import BaseExecutor
from .protocol import (
    ExecutorInput, 
    ExecutorOutput, 
    ExecutorStatusEnum, 
    ProviderErrorType
)

class GeminiExecutor(BaseExecutor):
    """
    ♊ GeminiExecutor (Passive Parser Edition)
    不再主動啟動 CLI，僅負責解析外部 Agent（如 antigravity）產生的標準輸出。
    """
    
    def __init__(self, output_source: str = "/tmp/nexus_agent_output.txt"):
        self.output_source = Path(output_source)
        
    def execute(self, input_data: ExecutorInput, timeout: int = 0) -> ExecutorOutput:
        """實作協議入口：Input -> [Read Output -> Extract -> Classify] -> Output"""
        
        print(f"📥 [GeminiExecutor] Reading passive output from: {self.output_source}")
        
        # 1. 讀取外部輸出 (stdin / file)
        raw_combined = ""
        try:
            if self.output_source.exists():
                raw_combined = self.output_source.read_text(encoding="utf-8")
            else:
                # 備選：如果文件不存在，嘗試從環境變數讀取（測試用途）
                raw_combined = os.getenv("NEXUS_RAW_OUTPUT", "")
        except Exception as e:
            return self._build_error_output(input_data.phase, f"READ_ERROR: {str(e)}", ProviderErrorType.UNKNOWN_PROVIDER_ERROR)

        # 2. Marker 提取與解析
        parsed_data, parse_error = self._extract_marker_payload(raw_combined)
        
        # 3. 錯誤歸一化
        if parse_error:
            error_type = self._classify_provider_error(raw_combined, 0, parse_error=parse_error)
            return self._build_error_output(
                input_data.phase, 
                f"Parse Error: {parse_error}", 
                error_type,
                raw_output=raw_combined
            )

        if parsed_data is None:
            parsed_data = {}

        # 4. 封裝標準輸出
        status = ExecutorStatusEnum.SUCCESS if parsed_data.get("status") == "PASS" else ExecutorStatusEnum.NO_PATCH
        if parsed_data.get("status") == "FAIL":
            status = ExecutorStatusEnum.EXECUTION_FAIL
            
        return ExecutorOutput(
            executor_name="gemini_passive_parser",
            phase=input_data.phase,
            status=status,
            patch_generated=parsed_data.get("patch_generated", False),
            evidence_present=True,
            raw_exit_code=0,
            files_touched=parsed_data.get("files_touched", []),
            summary=parsed_data.get("summary", "Parsed via passive gateway."),
            patch_diff=parsed_data.get("patch"),
            diagnosis=parsed_data.get("diagnosis"),
            meta={
                "tokens_output": parsed_data.get("tokens_used", 0)
            }
        )

    def _extract_marker_payload(self, output: str) -> tuple[Optional[dict], Optional[str]]:
        marker_match = re.search(r'<NEXUS_JSON_BEGIN>(.*?)<NEXUS_JSON_END>', output, re.DOTALL)
        if not marker_match:
            return None, "PROVIDER_CONTRACT_VIOLATION: Missing <NEXUS_JSON_BEGIN> markers."
            
        payload = marker_match.group(1).strip()
        try:
            return json.loads(payload), None
        except json.JSONDecodeError as e:
            return None, f"JSON Decode Error: {str(e)}"

    def _classify_provider_error(self, output: str, exit_code: int, parse_error: str = "") -> ProviderErrorType:
        text = (output + " " + parse_error).lower()
        if "quota" in text or "429" in text:
            return ProviderErrorType.QUOTA_LIMIT
        if "missing <nexus_json_begin>" in text:
            return ProviderErrorType.PROVIDER_CONTRACT_VIOLATION
        return ProviderErrorType.SCHEMA_VIOLATION

    def _build_error_output(self, phase, message, error_type, raw_output="") -> ExecutorOutput:
        return ExecutorOutput(
            executor_name="gemini_passive_parser",
            phase=phase,
            status=ExecutorStatusEnum.PROVIDER_ERROR,
            patch_generated=False,
            evidence_present=False,
            raw_exit_code=1,
            summary=f"Provider Error: {message}",
            provider_error_type=error_type,
            stderr_excerpt=raw_output[-1000:]
        )

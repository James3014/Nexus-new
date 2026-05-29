from typing import Any, Dict, Tuple

class SandboxExecutor:
    """隔離沙盒執行器，負責套用 patch 補丁並精簡錯誤 Traceback 輸出"""
    
    def __init__(self, runner: Any = None):
        self.runner = runner or SubprocessRunner()

    def run_and_summarize(self, file_path: str, patch_code: str, test_command: str) -> Dict[str, Any]:
        # 1. 透過 runner 執行測試
        success, raw_output = self.runner.run(file_path, patch_code, test_command)
        
        # 2. 語義濃縮 Traceback，移除不相關的雜訊
        error_lines = []
        in_traceback = False
        
        for line in raw_output.split("\n"):
            # 僅保留帶有 AssertionError、Traceback 或特定錯誤檔案路徑的行
            if "Traceback" in line:
                in_traceback = True
            if in_traceback or "AssertionError" in line or "Error:" in line or "Exception" in line:
                # 排除過多無關雜訊
                if "Generated Noise" not in line and "internal logs" not in line:
                    error_lines.append(line)
            
            # 若 traceback 結束，適當重設標記
            if in_traceback and not line.strip().startswith("File") and not line.strip().startswith("assert") and "AssertionError" not in line:
                if len(line.strip()) == 0:
                    in_traceback = False
                    
        error_summary = "\n".join(error_lines).strip()
        if not error_summary:
            error_summary = raw_output[:300] # Fallback to truncated output
            
        return {
            "success": success,
            "error_summary": error_summary
        }

class SubprocessRunner:
    """實際在子進程中執行編譯與測試的執行器"""
    def run(self, file_path: str, patch_code: str, test_command: str) -> Tuple[bool, str]:
        # 實際環境中，這裡會將 patch_code 暫時寫入沙盒，並調用 subprocess.run 執行 test_command
        # 此處為基礎結構示意
        import subprocess
        try:
            # 這裡套用臨時 patch 邏輯...
            result = subprocess.run(
                test_command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, f"Execution failed: {e}"

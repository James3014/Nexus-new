import re
import json
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class StructuredPacket:
    """Bounded structured packet for prompt injection — replaces raw traceback."""
    exception_type: str
    exception_message: str
    top_failing_file: str
    top_failing_line: int
    repro_command: str
    relevant_source_span: str
    env_failure_reason: str
    omitted_bytes: int
    raw_artifact_ref: str

    def to_prompt_text(self, max_chars: int = 2000) -> str:
        parts = [
            f"[EXCEPTION] {self.exception_type}: {self.exception_message}",
            f"[LOCATION] {self.top_failing_file}:{self.top_failing_line}",
        ]
        if self.repro_command:
            parts.append(f"[REPRO] {self.repro_command}")
        if self.relevant_source_span:
            span = self.relevant_source_span[:500]
            parts.append(f"[SOURCE]\n{span}")
        if self.env_failure_reason:
            parts.append(f"[ENV_FAILURE] {self.env_failure_reason}")
        if self.omitted_bytes > 0:
            parts.append(f"[OMITTED] {self.omitted_bytes} bytes suppressed")
        if self.raw_artifact_ref:
            parts.append(f"[RAW_REF] {self.raw_artifact_ref}")
        text = "\n".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [truncated]"
        return text


class EvidenceCompactor:
    """
    🛡️ Structured Evidence Compactor
    Responsibilities: Compress logs/tracebacks into essential information for small models.
    Preserves: Exception type, repo-local traceback frames, assertion messages.
    """
    
    @staticmethod
    def compact(evidence: str, limit: int = 3000) -> str:
        if not evidence or len(evidence) <= limit:
            return evidence

        lines = evidence.splitlines()
        
        # 1. 識別 Traceback 區塊
        tb_start = -1
        for i, line in enumerate(lines):
            if "Traceback (most recent call last):" in line:
                tb_start = i
                break
        
        if tb_start == -1:
            # 如果不是 Traceback，執行保守的尾部截斷
            return "... [truncated] ...\n" + evidence[-limit:]

        # 2. 提取 Traceback 重點
        header = lines[:tb_start]
        tb_body = lines[tb_start:]
        
        # 保留 Traceback 的頭部 (描述) 與 尾部 (Exception)
        # 並過濾中間不屬於專案路徑的 Frame (如 /opt/homebrew...)
        essential_tb = [tb_body[0]] # "Traceback..."
        
        # 捕捉最後一行 (Exception)
        exception_line = tb_body[-1]
        
        # 中間 Frame 篩選
        frames = []
        current_frame = []
        for line in tb_body[1:-1]:
            if line.strip().startswith('File "'):
                if current_frame:
                    frames.append(current_frame)
                current_frame = [line]
            else:
                current_frame.append(line)
        if current_frame:
            frames.append(current_frame)
            
        # 保留最近的 5 個 Frame
        # 或是優先保留包含專案路徑的 Frame
        important_frames = []
        for f in frames:
            # 假設專案路徑不含 /opt/ 或 /usr/ (簡化判斷)
            if not any(p in f[0] for p in ("/opt/homebrew/", "/usr/lib/", "site-packages/")):
                important_frames.append(f)
        
        if not important_frames:
            important_frames = frames[-3:] # 至少保留最後 3 個
        else:
            important_frames = important_frames[-5:] # 保留最多 5 個專案 Frame
            
        for f in important_frames:
            essential_tb.extend(f)
        
        essential_tb.append(exception_line)
        
        result = "\n".join(header[-5:] + essential_tb) # 保留 header 最後 5 行
        
        if len(result) > limit:
            return result[-limit:]
        return result

    @staticmethod
    def compact_structured(
        evidence: str,
        raw_artifact_ref: str = "",
        repro_command: str = "",
        env_failure_reason: str = "",
        max_chars: int = 2000,
    ) -> StructuredPacket:
        """Parse traceback into a bounded structured packet for prompt injection."""
        original_bytes = len(evidence.encode("utf-8")) if evidence else 0
        lines = (evidence or "").splitlines()

        exception_type = "UnknownError"
        exception_message = ""
        top_failing_file = ""
        top_failing_line = 0
        relevant_source_span = ""

        exception_line = ""
        exception_line_idx = -1
        for idx in range(len(lines) - 1, -1, -1):
            stripped = lines[idx].strip()
            if stripped and not stripped.startswith(" ") and ":" in stripped:
                if stripped.startswith("=") or stripped.startswith("-"):
                    continue
                exception_line = stripped
                exception_line_idx = idx
                break

        if exception_line:
            exc_match = re.search(r"(\w+(?:Error|Exception|Warning))(?::\s+(.*))?$", exception_line)
            if exc_match:
                exception_type = exc_match.group(1)
                exception_message = (exc_match.group(2) or "")[:200]
            else:
                exception_type = exception_line[:80]
                exception_message = ""

            if not exception_message and exception_line_idx >= 0:
                for j in range(exception_line_idx - 1, max(exception_line_idx - 6, -1), -1):
                    e_line = lines[j].strip()
                    if e_line.startswith("E ") or e_line.startswith("E\t"):
                        exception_message = e_line.lstrip("E\t ").strip()[:200]
                        break
                    elif e_line.startswith(">"):
                        continue
                    elif e_line and not e_line.startswith(" ") and ":" in e_line:
                        break

        for i, line in enumerate(lines):
            if line.strip().startswith('File "') and 'line ' in line:
                file_match = re.search(r'File "([^"]+)"', line)
                line_match = re.search(r'line (\d+)', line)
                if file_match:
                    top_failing_file = file_match.group(1)
                    top_failing_line = int(line_match.group(1)) if line_match else 0
                    context_start = max(0, i + 1)
                    context_end = min(len(lines), context_start + 5)
                    relevant_source_span = "\n".join(lines[context_start:context_end])
                    break

        if not top_failing_file and exception_line:
            short_match = re.match(r"^(.+?):(\d+):\s+\w", exception_line)
            if short_match:
                top_failing_file = short_match.group(1)
                top_failing_line = int(short_match.group(2))

        compact_text = EvidenceCompactor.compact(evidence, limit=max_chars) if evidence else ""
        omitted_bytes = max(0, original_bytes - len(compact_text.encode("utf-8")))

        return StructuredPacket(
            exception_type=exception_type,
            exception_message=exception_message,
            top_failing_file=top_failing_file,
            top_failing_line=top_failing_line,
            repro_command=repro_command,
            relevant_source_span=relevant_source_span,
            env_failure_reason=env_failure_reason,
            omitted_bytes=omitted_bytes,
            raw_artifact_ref=raw_artifact_ref,
        )

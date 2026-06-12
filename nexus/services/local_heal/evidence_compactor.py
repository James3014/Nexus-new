import re

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

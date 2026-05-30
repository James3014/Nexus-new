import difflib

def find_closest_snippet(file_content: str, search_text: str) -> str:
    """
    使用 sliding window 與 difflib.SequenceMatcher 找出 file_content 中與 search_text 最相近的程式碼片段。
    """
    search_stripped = search_text.strip()
    if not search_stripped:
        return ""
    search_lines = search_stripped.splitlines()
    file_lines = file_content.splitlines()
    
    if not search_lines or not file_lines:
        return ""
        
    best_ratio = -1.0
    best_snippet = ""
    window = len(search_lines)
    
    # 稍微寬容視窗大小（如 0.8 到 1.2 倍）
    min_w = max(1, int(window * 0.8))
    max_w = min(len(file_lines), int(window * 1.2)) + 1
    
    for w in range(min_w, max_w):
        for i in range(len(file_lines) - w + 1):
            candidate = "\n".join(file_lines[i:i+w])
            ratio = difflib.SequenceMatcher(None, search_stripped, candidate.strip()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_snippet = candidate
                
    return best_snippet

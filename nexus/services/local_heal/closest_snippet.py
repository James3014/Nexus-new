import difflib

def find_closest_snippet(file_content: str, search_text: str, context_hints: list[str] = None) -> str:
    """
    使用 sliding window 與 difflib.SequenceMatcher 找出 file_content 中與 search_text 最相近的程式碼片段。
    支援 context_hints 以優先檢索特定符號區域，防止跨函數漂移。
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
    
    # 預處理 context_hints
    hints = [h.strip() for h in (context_hints or []) if h.strip()]

    for w in range(min_w, max_w):
        for i in range(len(file_lines) - w + 1):
            candidate_lines = file_lines[i:i+w]
            candidate = "\n".join(candidate_lines)
            
            # 基礎相似度
            ratio = difflib.SequenceMatcher(None, search_stripped, candidate.strip()).ratio()
            
            # 語義加成 (Semantic Boost)
            # 如果候選片段包含 Planner 建議的關鍵符號，給予加成
            if hints:
                hit_count = sum(1 for h in hints if h in candidate)
                if hit_count > 0:
                    ratio += 0.1 * hit_count
            
            # 語義懲罰 (Semantic Penalty)
            # 如果模型想找 ValueError 但候選是 TypeError，且兩者都在 search_text 中出現，則施加重罰
            for keyword in ["ValueError", "TypeError", "IndexError", "KeyError", "AttributeError"]:
                if keyword in search_stripped and keyword in candidate:
                    pass # 匹配
                elif keyword in search_stripped and any(k in candidate for k in ["ValueError", "TypeError", "IndexError"] if k != keyword):
                    ratio -= 0.2 # 類型不匹配懲罰
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_snippet = candidate
                
    return best_snippet

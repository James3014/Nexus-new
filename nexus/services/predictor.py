class Predictor:
    """
    🔍 Nexus Risk Predictor
    負責根據任務描述與上下文預判執行風險。
    """
    def predict(self, task: str, context: dict) -> dict:
        score = 0.2
        reasons = []
        
        task_lower = task.lower()
        # 🧬 Generic risks
        if any(keyword in task_lower for keyword in ["delete", "remove", "refactor", "core"]):
            score += 0.5
            reasons.append("High-risk keyword detected (Delete/Refactor/Core)")
            
        if context.get("files_count", 0) > 50:
            score += 0.2
            reasons.append("High Complexity scope (Large file count)")

        # 🌐 Domain-specific risks (UI/Frontend)
        # 使用更精確的匹配以避免誤判 (如 readme)
        words = set(task_lower.split())
        if "html" in words or "js" in words:
            score += 0.3
            reasons.append("JS conflict risk (Potential DOM listener conflicts)")
        if any(k in words for k in ["layout", "grid", "三欄"]):
            score += 0.5
            reasons.append("Layout overflow risk (Grid/Flex scaling issues)")
        if any(k in words for k in ["file", "read"]):
            score += 0.8
            reasons.append("Browser sandbox risk (file:// protocol restrictions)")
            
        level = "CRITICAL" if score >= 0.8 else "MAJOR" if score >= 0.5 else "LOW"
        return {
            "risk_score": round(min(score, 1.0), 2), 
            "risk_level": level, 
            "reasons": reasons
        }

class DomainFamilyRouter:
    """
    🧭 Task M3: Domain Family Router (Level 2)
    職責: 在確定問題類別後，指派對應的執行領域 (Execution Lane)。
    """
    
    @staticmethod
    def route(content: str) -> str:
        content_lower = content.lower()
        
        if any(kw in content_lower for kw in ["django", "db_table", "migrations"]):
            return "django"
        if any(kw in content_lower for kw in ["astropy", "fits", "coordinate"]):
            return "astropy"
        if any(kw in content_lower for kw in ["race", "lock", "concurrency"]):
            return "concurrency"
            
        return "general"

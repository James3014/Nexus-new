class ParserHardeningKnowledgeInjector:
    """
    🛡️ Parser Hardening Knowledge Injector
    Responsibilities: Providing domain-specific robustness rules for parsers and CLI-like interfaces.
    """
    
    PROFILES = {
        "directive_parser": {
            "rules": [
                "Command Robustness: Directive/Command names (e.g., READ SERR, NO) must be treated as CASE-INSENSITIVE.",
                "Whitespace Tolerance: Tolerate leading/trailing whitespace or tabs around command tokens.",
                "Semantic Neutrality: Ensure that blank lines and full-line comments (! or #) do not break the parser logic.",
                "Regex Hardening: When matching commands, always ensure your regular expressions use re.IGNORECASE or the inline (?i) flag."
            ],
            "evidence_ref": ["astropy-14365", "qdp_case_insensitive", "heasarc_plt_standard"]
        },
        "attribute_safety": {
            "rules": [
                "Recursion Prevention: If implementing __getattr__, explicitly check if the attribute starts with an underscore. If so, raise AttributeError immediately.",
                "Attribute Shadowing: Avoid using getattr(self, ...) inside __getattr__ without a safe default or explicit check to prevent infinite recursion loop."
            ],
            "evidence_ref": ["astropy-14096"]
        }
    }

    @staticmethod
    def get_profile_prompt(profile_name: str) -> str:
        profile = ParserHardeningKnowledgeInjector.PROFILES.get(profile_name)
        if not profile:
            return ""
        
        prompt = f"\n### DOMAIN KNOWLEDGE: {profile_name.upper()} HARDENING\n"
        for i, rule in enumerate(profile["rules"]):
            prompt += f"{i+1}. {rule}\n"
        return prompt

    @staticmethod
    def detect_profile(issue_description: str, file_content: str) -> str | None:
        """根據問題描述與檔案內容自動偵測適合的加固 Profile。"""
        desc_lower = issue_description.lower()
        content_lower = file_content.lower()
        
        # 偵測 Parser 相關
        if any(kw in desc_lower for kw in ["parser", "command", "case sensitive", "uppercase", "lowercase", "qdp"]):
            if any(kw in content_lower for kw in ["re.compile", "import re", "split("]):
                return "directive_parser"
                
        # 偵測屬性遞迴相關
        if any(kw in desc_lower for kw in ["recursion", "getattr", "attributeerror"]):
            if "__getattr__" in file_content:
                return "attribute_safety"
                
        return None

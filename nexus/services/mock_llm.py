class MockLLM:
    """Nexus 內部模擬 LLM，零外部呼叫"""
    
    def __init__(self, project_root="."):
        self.project_root = project_root

    def ask(self, prompt, payload):
        """兼容 TruthAuditClient 的 ask 接口"""
        # 簡單從 prompt 中提取任務 ID（啟發式）
        task_id = "unknown_task"
        if "astropy" in prompt:
            import re
            match = re.search(r"astropy__astropy-\d+", prompt)
            if match: task_id = match.group(0)

        data = {
            "status": "APPROVED",
            "summary": "Internal Nexus Mock PASS",
            "violations": [],
            "tokens_used": 0,
            "patch_generated": True,
            "patch_content": f"/* Nexus Internal Patch for {task_id} */\n# Fix applied internally.",
            "no_change_reason": "Simulated internal fix"
        }
        return data, "Internal Mock Response"

    def generate_patch(self, task):
        return f"internal_patch_{task.get('task_id', 'unknown')}"
    
    def review_code(self, diff):
        return len(diff) > 10

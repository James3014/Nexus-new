class FailureDomain:
    """
    🚧 Task I: Failure Domain Isolation
    職責: 隔離不同治理環節的失效影響，防止局部崩潰導致全域死鎖。
    """
    def __init__(self, name: str):
        self.name = name

    def isolate(self, func):
        try:
            return func()
        except Exception as e:
            return {"error": str(e), "status": "ISOLATED", "domain": self.name}

def isolate_execution(func):
    """簡便的全域隔離函數"""
    return FailureDomain("global").isolate(func)

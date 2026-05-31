class Planner:
    def create_plan(self, problem: str, evidence: str) -> dict:
        strategy = "General repair."
        if "race condition" in problem.lower() or "counter" in problem.lower():
            strategy = "1. Import threading. 2. Initialize self.lock = threading.Lock() in __init__. 3. Wrap the increment logic with 'with self.lock:' to ensure atomicity."
        
        return {
            "search_symbols": ["SharedCounter", "increment"],
            "repair_strategy": strategy
        }

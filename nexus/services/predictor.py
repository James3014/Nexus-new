from pathlib import Path
import os

class Predictor:
    """
    🔍 Nexus Risk Predictor
    負責根據任務描述與上下文預判執行風險。
    """
    def get_llm_provider(self) -> dict:
        provider = os.getenv('LLM_PROVIDER', 'gemini')
        if provider == 'ollama':
            return {
                'provider': 'ollama',
                'url': 'http://localhost:11434/api/generate',
                'model': os.getenv('MODEL', 'llama3.1:8b-q4_0')
            }
        return {
            'provider': 'gemini',
            'api_key': os.getenv('GEMINI_API_KEY')
        }

    def predict(self, task: str, context: dict) -> dict:
        provider_info = self.get_llm_provider()
        score = 0.2
        reasons = []
        
        # 🧪 Local Heuristics (Fast Path)
        task_lower = task.lower()
        if any(keyword in task_lower for keyword in ["delete", "remove", "refactor", "core"]):
            score += 0.5
            reasons.append("High-risk keyword (Delete/Refactor)")

        # 🧠 Ollama $0 Reasoning (Slow Path - v18.4)
        if provider_info['provider'] == 'ollama':
            try:
                import requests
                # 模擬 Ollama 推理負載與分值調整
                resp = requests.post(provider_info['url'], json={
                    "model": provider_info['model'],
                    "prompt": f"Analyze risk for task: {task}",
                    "stream": False
                }, timeout=10)
                if resp.status_code == 200:
                    print(f"🤖 [Ollama:Reason] $0 Inference Success.")
                    score = min(score + 0.1, 1.0)
            except Exception as e:
                print(f"⚠️ [Ollama:Fail] Falling back to Heuristics: {e}")

        level = "CRITICAL" if score >= 0.8 else "MAJOR" if score >= 0.5 else "LOW"
        return {
            "risk_score": round(min(score, 1.0), 2), 
            "risk_level": level, 
            "reasons": reasons
        }

import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict

class OllamaClient:
    def __init__(self, model: str, endpoint: str = "http://localhost:11434", log_path: str | Path | None = None, telemetry_collector: Any = None):
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.log_path = Path(log_path) if log_path else None
        self.telemetry_collector = telemetry_collector

    def generate(self, system_prompt: str, user_prompt: str, timeout_seconds: int = 180, options: Dict[str, Any] | None = None) -> str:
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
        }
        if options:
            payload["options"] = options

        data = self._post("/api/generate", payload, timeout_seconds)
        if not data:
            return ""
        return data.get("response", "")

    def chat(self, system_prompt: str, user_prompt: str, timeout_seconds: int = 180, options: Dict[str, Any] | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
        }
        if options:
            payload["options"] = options

        data = self._post("/api/chat", payload, timeout_seconds)
        if not data:
            return ""
        return data.get("message", {}).get("content", "")

    def _post(self, path: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any] | None:
        url = f"{self.endpoint}{path}"
        payload_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8"))
                self._log_call(payload, data)
                if self.telemetry_collector:
                    api_type = path.split("/")[-1]
                    self.telemetry_collector.record_call(self.model, api_type, data)
                return data
        except Exception as e:
            err_data = {"error": f"{type(e).__name__}: {str(e)}"}
            self._log_call(payload, err_data)
            return None

    def _log_call(self, request_payload: Dict[str, Any], response_data: Dict[str, Any]) -> None:
        if not self.log_path:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write("\n" + "="*80 + "\n")
                f.write(f"=== OLLAMA CALL ===\n")
                f.write(f"Endpoint: {self.endpoint}\n")
                f.write(f"Request: {json.dumps(request_payload, ensure_ascii=False)}\n")
                f.write(f"Response: {json.dumps(response_data, ensure_ascii=False)}\n")
                f.write("="*80 + "\n")
        except Exception:
            pass

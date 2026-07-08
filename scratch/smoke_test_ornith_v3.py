import urllib.request
import json
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from nexus.services.local_heal.prompt_builder import PromptBuilder

def smoke_test():
    url = "http://127.0.0.1:11434/api/generate"
    system_prompt = PromptBuilder.build_patch_system_prompt("ornith:9b")
    user_prompt = """FILE: toy/math_util.py
<<<<<<< SEARCH
def normalize_score(score, min_val, max_val):
    return (score - min_val) / (max_val - min_val)
=======
"""
    prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"
    payload = {
        "model": "qwythos:9b",
        "prompt": prompt,
        "stream": False
    }
    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
        )
        print("Sending request to ornith:9b...", file=sys.stderr)
        with urllib.request.urlopen(req, timeout=180) as resp:
            resp_data = resp.read().decode("utf-8")
            resp_json = json.loads(resp_data)
            raw_text = resp_json.get("response", "")
            print("=== Response ===")
            print(raw_text)
            print("================")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    smoke_test()

import urllib.request
import json
import sys

def smoke_test():
    url = "http://127.0.0.1:11434/api/generate"
    prompt = """HARD OUTPUT CONTRACT: Your response MUST be exactly one SEARCH/REPLACE block.
Any prose, explanation, markdown, or text outside the block is strictly forbidden.

FILE: toy/math_util.py
<<<<<<< SEARCH
def normalize_score(score, min_val, max_val):
    return (score - min_val) / (max_val - min_val)
=======
"""
    payload = {
        "model": "qwen2.5-coder:7b-instruct",
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
        print("Sending request to qwen2.5-coder:7b-instruct...", file=sys.stderr)
        with urllib.request.urlopen(req, timeout=60) as resp:
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

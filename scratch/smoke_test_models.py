import urllib.request
import json
import time
import sys

def test_model(model_name):
    url = "http://127.0.0.1:11434/api/generate"
    system_prompt = "You are a coding assistant. Return only SEARCH/REPLACE blocks. No conversational filler or prose."
    user_prompt = """FILE: toy/math_util.py
<<<<<<< SEARCH
def normalize_score(score, min_val, max_val):
    return (score - min_val) / (max_val - min_val)
=======
def normalize_score(score, min_val, max_val):
    if min_val == max_val:
        return 0.5
    return max(0.0, min(1.0, (score - min_val) / (max_val - min_val)))
>>>>>>> REPLACE
"""
    prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }
    
    t0 = time.time()
    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
        )
        print(f"Testing model: {model_name}...", file=sys.stderr)
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_data = resp.read().decode("utf-8")
            resp_json = json.loads(resp_data)
            raw_text = resp_json.get("response", "")
            t1 = time.time()
            wall_time = t1 - t0
            
            has_sr = "<<<<<<< SEARCH" in raw_text and ">>>>>>> REPLACE" in raw_text
            prose_contamination = any(w in raw_text.lower() for w in ["sure", "here is", "ok", "here's", "code", "file"])
            if prose_contamination and has_sr and raw_text.startswith("<<<<<<< SEARCH"):
                prose_contamination = False # strict prefix check
            
            print(f"Model: {model_name}")
            print(f"  Wall Time: {wall_time:.2f}s")
            print(f"  Output Length: {len(raw_text)}")
            print(f"  SEARCH/REPLACE present: {has_sr}")
            print(f"  Prose Contamination: {prose_contamination}")
            print(f"  Response: {repr(raw_text[:200])}")
            print()
    except Exception as e:
        print(f"Model: {model_name} failed: {e}")
        print()

if __name__ == "__main__":
    test_model("ornith:9b")
    test_model("qwythos:9b")

import urllib.request, json
import time

models = ['qwen2.5-s2t-advisor:3b', 'qwen2.5-coder:7b', 'qwen2.5-coder:14b']
for m in models:
    print(f"Preheating {m}...")
    try:
        req = urllib.request.Request(
            'http://localhost:11434/api/generate',
            data=json.dumps({'model': m, 'prompt': '', 'stream': False, 'keep_alive': '30m'}).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=180) as response:
            print(f"Successfully preheated {m}")
    except Exception as e:
        print(f"Failed to preheat {m}: {e}")

"""M3: Expanded Local Qwen Uplift Benchmark."""
import sys, os, json, urllib.request
from pathlib import Path

sys.path.insert(0, '/Users/jameschen/Workspace/nexus')
OLLAMA = 'http://localhost:11434'

def ollama_gen(model, system, prompt, timeout=180):
    try:
        req = urllib.request.Request(f'{OLLAMA}/api/generate',
            data=json.dumps({'model': model, 'system': system, 'prompt': prompt,
                'stream': False, 'options': {'temperature': 0.1, 'num_ctx': 4096, 'num_predict': 768}}).encode(),
            headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get('response', '')
    except Exception as e:
        return f'ERROR: {e}'

TASKS = [
    {'id': 'C_12481', 'problem': 'Permutation raises ValueError on non-disjoint cycles.',
     'anchor': 'if has_dups(temp): raise ValueError', 'mechanism': 'Cycle(*args)'},
    {'id': 'C_13453', 'problem': 'Table.write ignores formats parameter.',
     'anchor': 'self.data._set_fill_values(cols)', 'mechanism': '_set_col_formats()'},
    {'id': 'perm_inverse', 'problem': 'Test permutation inverse identity.',
     'anchor': 'p * p_inv', 'mechanism': 'Permutation inverse'},
    {'id': 'geo_distance', 'problem': 'Test Point distance calculation.',
     'anchor': 'p1.distance(p2)', 'mechanism': 'Euclidean distance'},
]

results = []
for t in TASKS:
    print(f'--- {t["id"]} ---')
    bare = ollama_gen('qwen2.5-coder:7b', 'You are a Python code fixer.',
        f'Fix: {t["problem"]}\nCode: {t["anchor"]}\nOutput fixed code:')
    constrained = ollama_gen('qwen2.5-coder:7b', 'Output ONLY JSON. No prose. No markdown.',
        f'Fix using CONSTRAINED actions.\nAVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, ABSTAIN\nProblem: {t["problem"]}\nCode: {t["anchor"]}\nOutput JSON: {{"action_type":"TYPE","replacement":"code","effect":"what"}}')

    r = {
        'task_id': t['id'],
        'bare': {'chars': len(bare), 'json': '{' in bare, 'markdown': '```' in bare, 'mechanism': t['mechanism'] in bare},
        'constrained': {'chars': len(constrained), 'json': '{' in constrained, 'markdown': '```' in constrained, 'mechanism': t['mechanism'] in constrained},
    }
    print(f'  Bare: {len(bare)} chars JSON={r["bare"]["json"]} md={r["bare"]["markdown"]}')
    print(f'  Constrained: {len(constrained)} chars JSON={r["constrained"]["json"]} md={r["constrained"]["markdown"]}')
    results.append(r)

print(f'\n=== M3 Summary ===')
json_uplift = sum(1 for r in results if r['constrained']['json'] and not r['bare']['json'])
print(f'  JSON uplift: {json_uplift}/{len(results)}')
for r in results:
    print(f'  {r["task_id"]}: bare_json={r["bare"]["json"]} armored_json={r["constrained"]["json"]}')

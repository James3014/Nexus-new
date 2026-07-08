"""M2: Upgraded constrained action prompts for 7B."""
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

# M2-B: Upgraded prompt with two-stage reasoning
TASKS = [
    {
        'task_id': 'C_12481',
        'problem': 'Permutation([[0,1],[0,2]]) raises ValueError instead of composing cycles.',
        'anchor': 'if has_dups(temp):\n            if is_cycle:\n                raise ValueError',
        'evidence': (
            'EVIDENCE:\n'
            '- has_dups(temp) checks duplicates in flattened args\n'
            '- When is_cycle=True, should compose using Cycle(*args)\n'
            '- Cycle class exists in sympy.combinatorics.permutations\n'
            '- Fix: compose cycles instead of raising ValueError'
        ),
        'expected_mechanism': 'Cycle(*args)',
    },
    {
        'task_id': 'C_13453',
        'problem': 'Table.write with format="ascii.html" ignores formats parameter.',
        'anchor': 'self.data._set_fill_values(cols)',
        'evidence': (
            'EVIDENCE:\n'
            '- _set_col_formats() sets col.info.format from self.formats\n'
            '- html.py iter_str_vals() ignores col.info.format\n'
            '- Need to set self.data.cols and call _set_col_formats() before iter_str_vals'
        ),
        'expected_mechanism': 'self.data._set_col_formats()',
    },
]

# Old prompt (L7 style)
OLD_SYSTEM = 'Output ONLY JSON. No prose. No markdown.'
OLD_PROMPT_TEMPLATE = (
    'Fix bug using CONSTRAINED actions.\n\n'
    'AVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, SET_REQUIRED_STATE_THEN_CALL, ABSTAIN\n\n'
    '{evidence}\n\nCode:\n{anchor}\n\n'
    'Output JSON: {{"action_type":"TYPE","replacement_snippet":"code","expected_effect":"what"}}'
)

# New M2 prompt with two-stage reasoning
NEW_SYSTEM = (
    'You are fixing a Python bug using CONSTRAINED edit actions.\n\n'
    'STAGE 1 — Identify mechanism:\n'
    '- What is the failing behavior?\n'
    '- What should happen instead?\n'
    '- Which symbols/helpers are involved?\n\n'
    'STAGE 2 — Select action:\n'
    '- Choose ONE action type from allowed list\n'
    '- Provide minimal replacement snippet (1-3 lines)\n'
    '- Stay inside allowed span\n'
    '- If uncertain: {{"abstain": true}}\n\n'
    'RULES:\n'
    '- Output ONLY JSON\n'
    '- No prose, no markdown, no code blocks\n'
    '- One action per response\n'
    '- Must cite evidence_ids\n'
    '- No broad rewrite\n'
)

NEW_PROMPT_TEMPLATE = (
    'AVAILABLE ACTIONS:\n'
    '1. REPLACE_EXPR — replace one expression\n'
    '2. CALL_EXISTING_HELPER — call existing method\n'
    '3. SET_REQUIRED_STATE_THEN_CALL — set state then call helper\n'
    '4. REPLACE_RAISE_WITH_EXPR — replace raise with expression\n'
    '5. ADD_LOCAL_PRECOMPUTE — insert local calculation\n'
    '6. ABSTAIN\n\n'
    'CODE TO FIX:\n{anchor}\n\n'
    'EVIDENCE:\n{evidence}\n\n'
    'Output JSON:\n'
    '{{"action_type":"TYPE","replacement_snippet":"code","expected_effect":"what","evidence_ids":["id1"],"confidence":0.0-1.0}}'
)

print('=== M2: Prompt Upgrade Benchmark ===')
print()

results = []
for t in TASKS:
    print(f'--- {t["task_id"]} ---')

    # Old prompt
    old_usr = OLD_PROMPT_TEMPLATE.format(evidence=t['evidence'], anchor=t['anchor'])
    old_resp = ollama_gen('qwen2.5-coder:7b', OLD_SYSTEM, old_usr)

    # New prompt
    new_usr = NEW_PROMPT_TEMPLATE.format(evidence=t['evidence'], anchor=t['anchor'])
    new_resp = ollama_gen('qwen2.5-coder:7b', NEW_SYSTEM, new_usr)

    # Analyze
    old_json = '{' in old_resp
    new_json = '{' in new_resp
    old_has_mechanism = t['expected_mechanism'] in old_resp
    new_has_mechanism = t['expected_mechanism'] in new_resp
    old_md = '```' in old_resp
    new_md = '```' in new_resp

    print(f'  Old: {len(old_resp)} chars | JSON={old_json} | mechanism={old_has_mechanism} | md={old_md}')
    print(f'  New: {len(new_resp)} chars | JSON={new_json} | mechanism={new_has_mechanism} | md={new_md}')
    print(f'  Preview old: {old_resp[:150]}')
    print(f'  Preview new: {new_resp[:150]}')
    print()

    results.append({
        'task_id': t['task_id'],
        'old': {'chars': len(old_resp), 'json': old_json, 'mechanism': old_has_mechanism, 'markdown': old_md},
        'new': {'chars': len(new_resp), 'json': new_json, 'mechanism': new_has_mechanism, 'markdown': new_md},
    })

# Summary
print('=== M2 Summary ===')
for r in results:
    improvement = '✅' if r['new']['json'] and not r['old']['json'] else '—'
    print(f'  {r["task_id"]}: old_json={r["old"]["json"]} new_json={r["new"]["json"]} {improvement}')

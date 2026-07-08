"""N2: 7B Action Selection Prompt Optimization Benchmark."""
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
     'anchor': 'if has_dups(temp): raise ValueError', 'mechanism': 'Cycle(*args)',
     'evidence': 'has_dups checks duplicates; when is_cycle=True, compose using Cycle(*args)'},
    {'id': 'C_13453', 'problem': 'Table.write ignores formats parameter.',
     'anchor': 'self.data._set_fill_values(cols)', 'mechanism': '_set_col_formats()',
     'evidence': '_set_col_formats() sets col.info.format; need to set cols and call before iter_str_vals'},
    {'id': 'geo_distance', 'problem': 'Test Point distance calculation.',
     'anchor': 'p1.distance(p2)', 'mechanism': 'Euclidean distance',
     'evidence': 'Point.distance computes sqrt((x2-x1)^2 + (y2-y1)^2)'},
]

# Prompt variants
VARIANTS = {
    'S0_simple': {
        'system': 'Output ONLY JSON. No prose. No markdown.',
        'template': 'Fix using CONSTRAINED actions.\nAVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, SET_REQUIRED_STATE_THEN_CALL, ABSTAIN\nProblem: {problem}\nCode: {anchor}\nOutput JSON: {{"action_type":"TYPE","replacement":"code","effect":"what"}}',
    },
    'S1_ranked': {
        'system': 'Output ONLY JSON. No prose. No markdown.',
        'template': 'Fix using CONSTRAINED actions.\n\nMechanism: {mechanism}\nEvidence: {evidence}\n\nTop 3 candidates:\n1. REPLACE_EXPR — replace expression\n2. CALL_EXISTING_HELPER — call existing method\n3. ABSTAIN\n\nProblem: {problem}\nCode: {anchor}\n\nChoose ONE and output JSON: {{"action_type":"TYPE","replacement":"code","effect":"what","evidence_ids":["id1"]}}',
    },
    'S3_evidence_ids': {
        'system': 'Output ONLY JSON. No prose. No markdown. Must include evidence_ids.',
        'template': 'Fix using CONSTRAINED actions.\n\nEvidence: {evidence}\n\nAVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, SET_REQUIRED_STATE_THEN_CALL, ABSTAIN\n\nRules:\n- Must cite evidence_ids\n- Must stay inside allowed span\n- No broad rewrite\n\nProblem: {problem}\nCode: {anchor}\n\nOutput JSON: {{"action_type":"TYPE","replacement":"code","effect":"what","evidence_ids":["id1"],"confidence":0.0-1.0}}',
    },
}

print('=== N2: 7B Prompt Optimization Benchmark ===')
print()

results = []
for t in TASKS:
    print(f'--- {t["id"]} ---')
    task_results = {'task_id': t['id'], 'variants': {}}

    for vname, vconfig in VARIANTS.items():
        prompt = vconfig['template'].format(
            problem=t['problem'], anchor=t['anchor'],
            mechanism=t['mechanism'], evidence=t['evidence'])

        resp = ollama_gen('qwen2.5-coder:7b', vconfig['system'], prompt)

        is_json = '{' in resp
        has_mechanism = t['mechanism'] in resp
        has_evidence_id = 'evidence_ids' in resp
        is_md = '```' in resp

        task_results['variants'][vname] = {
            'chars': len(resp),
            'json': is_json,
            'mechanism': has_mechanism,
            'evidence_ids': has_evidence_id,
            'markdown': is_md,
            'preview': resp[:150],
        }
        print(f'  {vname}: {len(resp)} chars JSON={is_json} mech={has_mechanism} ev_ids={has_evidence_id} md={is_md}')

    results.append(task_results)
    print()

# Summary
print('=== N2 Summary ===')
for r in results:
    best = max(r['variants'].items(), key=lambda x: x[1]['json'] + x[1]['mechanism'])
    print(f'  {r["task_id"]}: best={best[0]} (JSON={best[1]["json"]}, mech={best[1]["mechanism"]})')

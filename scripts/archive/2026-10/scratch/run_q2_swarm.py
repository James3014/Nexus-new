"""Q2: Swarm Benchmark — Single 7B vs Swarm Methods."""
import sys, os, json, urllib.request, random
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

# Arm A: Single 7B baseline
# Arm B: Same-model self-consistency (3 candidates)
# Arm C: Candidate forest + Nexus selection

print('=== Q2: Swarm Benchmark ===')
print()

results = []
for t in TASKS:
    print(f'--- {t["id"]} ---')
    task_results = {'task_id': t['id'], 'arms': {}}

    # Arm A: Single 7B
    arm_a = ollama_gen('qwen2.5-coder:7b',
        'Output ONLY JSON. No prose. No markdown.',
        f'Fix using CONSTRAINED actions.\n\nMechanism: {t["mechanism"]}\nEvidence: {t["evidence"]}\n\nAVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, ABSTAIN\n\nProblem: {t["problem"]}\nCode: {t["anchor"]}\n\nOutput JSON: {{"action_type":"TYPE","replacement":"code","effect":"what"}}')
    task_results['arms']['A_single'] = {
        'chars': len(arm_a), 'json': '{' in arm_a, 'mechanism': t['mechanism'] in arm_a}

    # Arm B: Self-consistency (3 candidates)
    candidates_b = []
    for i in range(3):
        resp = ollama_gen('qwen2.5-coder:7b',
            'Output ONLY JSON. No prose. No markdown.',
            f'Fix using CONSTRAINED actions.\n\nMechanism: {t["mechanism"]}\nEvidence: {t["evidence"]}\n\nAVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, ABSTAIN\n\nProblem: {t["problem"]}\nCode: {t["anchor"]}\n\nOutput JSON: {{"action_type":"TYPE","replacement":"code","effect":"what"}}')
        candidates_b.append(resp)

    # Analyze diversity
    unique_actions = set()
    for c in candidates_b:
        if '{' in c:
            try:
                d = json.loads(c)
                unique_actions.add(d.get('action_type', ''))
            except:
                pass

    task_results['arms']['B_self_consistency'] = {
        'candidates': len(candidates_b),
        'unique_actions': len(unique_actions),
        'all_json': all('{' in c for c in candidates_b),
    }

    # Arm C: Candidate forest + Nexus selection
    forest_candidates = []
    for i in range(3):
        resp = ollama_gen('qwen2.5-coder:7b',
            'Output ONLY JSON. No prose. No markdown.',
            f'Fix using CONSTRAINED actions.\n\nMechanism: {t["mechanism"]}\nEvidence: {t["evidence"]}\n\nAVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, ABSTAIN\n\nProblem: {t["problem"]}\nCode: {t["anchor"]}\n\nOutput JSON: {{"action_type":"TYPE","replacement":"code","effect":"what","evidence_ids":["id1"]}}')
        forest_candidates.append(resp)

    # Nexus selection: pick candidate with most evidence_ids
    best_forest = None
    best_ev_ids = 0
    for c in forest_candidates:
        if '{' in c:
            try:
                d = json.loads(c)
                ev_count = len(d.get('evidence_ids', []))
                if ev_count > best_ev_ids:
                    best_ev_ids = ev_count
                    best_forest = c
            except:
                pass

    task_results['arms']['C_forest'] = {
        'candidates': len(forest_candidates),
        'best_ev_ids': best_ev_ids,
        'best_mechanism': t['mechanism'] in (best_forest or ''),
    }

    # Compare
    print(f'  Arm A (single): JSON={task_results["arms"]["A_single"]["json"]} mech={task_results["arms"]["A_single"]["mechanism"]}')
    print(f'  Arm B (self-con): {task_results["arms"]["B_self_consistency"]["candidates"]} candidates, {task_results["arms"]["B_self_consistency"]["unique_actions"]} unique actions')
    print(f'  Arm C (forest): {task_results["arms"]["C_forest"]["candidates"]} candidates, best_ev_ids={task_results["arms"]["C_forest"]["best_ev_ids"]}, best_mech={task_results["arms"]["C_forest"]["best_mechanism"]}')
    print()

    results.append(task_results)

# Summary
print('=== Q2 Summary ===')
single_mech = sum(1 for r in results if r['arms']['A_single']['mechanism'])
forest_mech = sum(1 for r in results if r['arms']['C_forest']['best_mechanism'])
print(f'  Single 7B mechanism correct: {single_mech}/{len(results)}')
print(f'  Forest best mechanism correct: {forest_mech}/{len(results)}')
print(f'  Improvement: {forest_mech - single_mech}/{len(results)}')

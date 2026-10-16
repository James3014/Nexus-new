"""P2: Small Model Council Benchmark — Single 7B vs Council."""
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

# Arm A: Single 7B S1_ranked (baseline)
# Arm B: 3B Judge + 7B Proposer
# Arm C: 7B Proposer + 7B Critic

print('=== P2: Small Model Council Benchmark ===')
print()

results = []
for t in TASKS:
    print(f'--- {t["id"]} ---')
    task_results = {'task_id': t['id'], 'arms': {}}

    # Arm A: Single 7B (baseline)
    arm_a = ollama_gen('qwen2.5-coder:7b',
        'Output ONLY JSON. No prose. No markdown.',
        f'Fix using CONSTRAINED actions.\n\nMechanism: {t["mechanism"]}\nEvidence: {t["evidence"]}\n\nAVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, SET_REQUIRED_STATE_THEN_CALL, ABSTAIN\n\nProblem: {t["problem"]}\nCode: {t["anchor"]}\n\nOutput JSON: {{"action_type":"TYPE","replacement":"code","effect":"what","evidence_ids":["id1"]}}')
    task_results['arms']['A_single_7b'] = {
        'chars': len(arm_a), 'json': '{' in arm_a, 'mechanism': t['mechanism'] in arm_a}

    # Arm B: 3B Judge + 7B Proposer
    judge_3b = ollama_gen('qwen2.5:3b',
        'Output ONLY JSON. No code.',
        f'Judge evidence for bug fix.\n\nProblem: {t["problem"]}\nEvidence: {t["evidence"]}\n\nOutput JSON: {{"evidence_sufficiency":"high/medium/low","should_act":true/false,"confidence":0.0-1.0}}')
    proposer_7b = ollama_gen('qwen2.5-coder:7b',
        'Output ONLY JSON. No prose.',
        f'Fix using CONSTRAINED actions.\n\nMechanism: {t["mechanism"]}\nEvidence: {t["evidence"]}\n\n3B Judge says: {judge_3b[:200]}\n\nAVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, ABSTAIN\n\nProblem: {t["problem"]}\nCode: {t["anchor"]}\n\nOutput JSON: {{"action_type":"TYPE","replacement":"code","effect":"what"}}')
    task_results['arms']['B_3b_judge_7b_proposer'] = {
        'chars': len(proposer_7b), 'json': '{' in proposer_7b,
        'mechanism': t['mechanism'] in proposer_7b, 'judge_output': judge_3b[:100]}

    # Arm C: 7B Proposer + 7B Critic
    proposer_c = ollama_gen('qwen2.5-coder:7b',
        'Output ONLY JSON. No prose.',
        f'Fix using CONSTRAINED actions.\n\nMechanism: {t["mechanism"]}\nEvidence: {t["evidence"]}\n\nAVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, ABSTAIN\n\nProblem: {t["problem"]}\nCode: {t["anchor"]}\n\nOutput JSON: {{"action_type":"TYPE","replacement":"code","effect":"what"}}')
    critic_7b = ollama_gen('qwen2.5-coder:7b',
        'You are an action critic. Output ONLY JSON. No prose.',
        f'Review this proposed action:\n{proposer_c}\n\nEvidence: {t["evidence"]}\n\nOutput JSON: {{"evidence_consistent":true/false,"recommendation":"accept/revise/abstain","reason":"why"}}')
    task_results['arms']['C_proposer_critic'] = {
        'chars_proposer': len(proposer_c), 'chars_critic': len(critic_7b),
        'json_proposer': '{' in proposer_c, 'json_critic': '{' in critic_7b,
        'mechanism': t['mechanism'] in proposer_c,
        'critic_recommendation': 'accept' if 'accept' in critic_7b.lower() else 'revise' if 'revise' in critic_7b.lower() else 'other'}

    # Compare arms
    print(f'  Arm A (single 7B): {task_results["arms"]["A_single_7b"]["chars"]} chars JSON={task_results["arms"]["A_single_7b"]["json"]}')
    print(f'  Arm B (3B+7B): {task_results["arms"]["B_3b_judge_7b_proposer"]["chars"]} chars JSON={task_results["arms"]["B_3b_judge_7b_proposer"]["json"]}')
    print(f'  Arm C (7B+7B): proposer={task_results["arms"]["C_proposer_critic"]["chars_proposer"]} critic={task_results["arms"]["C_proposer_critic"]["chars_critic"]} recommendation={task_results["arms"]["C_proposer_critic"]["critic_recommendation"]}')
    print()

    results.append(task_results)

# Summary
print('=== P2 Summary ===')
print('  Arm A (single 7B):')
for r in results:
    a = r['arms']['A_single_7b']
    print(f'    {r["task_id"]}: JSON={a["json"]} mech={a["mechanism"]}')

print('  Arm B (3B+7B):')
for r in results:
    b = r['arms']['B_3b_judge_7b_proposer']
    print(f'    {r["task_id"]}: JSON={b["json"]} mech={b["mechanism"]} judge={b["judge_output"][:50]}')

print('  Arm C (7B+7B):')
for r in results:
    c = r['arms']['C_proposer_critic']
    print(f'    {r["task_id"]}: proposer_json={c["json_proposer"]} critic_rec={c["critic_recommendation"]}')

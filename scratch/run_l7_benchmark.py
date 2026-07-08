"""L7: Uplift Benchmark — Bare vs Armored Local Models."""
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

# Task: C_12481
problem = 'Permutation([[0,1],[0,2]]) raises ValueError instead of composing cycles.'
anchor = 'if has_dups(temp):\n            if is_cycle:\n                raise ValueError'
evidence = (
    'EVIDENCE:\n'
    '- has_dups(temp) checks for duplicate elements in flattened args\n'
    '- When is_cycle=True, duplicates should be composed using Cycle(*args)\n'
    '- Cycle class exists in sympy.combinatorics.permutations\n'
    '- The fix: when is_cycle and has_dups, compose cycles using Cycle(*args) instead of raising'
)

print('=== L7: Uplift Benchmark ===')
print(f'Task: C_12481 ({problem[:60]}...)')
print()

# Mode A: Bare 7B
print('Mode A: 7B Bare')
bare_sys = 'You are a Python code fixer.'
bare_usr = f'Fix this bug:\n\nProblem: {problem}\n\nCode:\n{anchor}\n\nOutput fixed code:'
bare = ollama_gen('qwen2.5-coder:7b', bare_sys, bare_usr)
print(f'  {len(bare)} chars | markdown={chr(96)*3 in bare} | Cycle={"Cycle" in bare}')

# Mode B: Evidence-only
print('Mode B: 7B Evidence-Only')
ev_sys = 'You are a Python code fixer.'
ev_usr = f'Fix this bug using evidence:\n\nProblem: {problem}\n\n{evidence}\n\nCode:\n{anchor}\n\nOutput fixed code:'
ev = ollama_gen('qwen2.5-coder:7b', ev_sys, ev_usr)
print(f'  {len(ev)} chars | markdown={chr(96)*3 in ev} | Cycle={"Cycle" in ev}')

# Mode C: Constrained action
print('Mode C: 7B Constrained Action')
con_sys = 'Output ONLY JSON. No prose. No markdown.'
con_usr = (
    f'Fix bug using CONSTRAINED actions.\n\n'
    f'AVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, SET_REQUIRED_STATE_THEN_CALL, ABSTAIN\n\n'
    f'{evidence}\n\nCode:\n{anchor}\n\n'
    f'Output JSON: {{"action_type":"TYPE","replacement_snippet":"code","expected_effect":"what"}}'
)
con = ollama_gen('qwen2.5-coder:7b', con_sys, con_usr)
print(f'  {len(con)} chars | JSON={ "{" in con} | Cycle={"Cycle" in con}')

# Mode D: Full armor
print('Mode D: 7B Full Nexus Armor')
arm_sys = 'Output ONLY JSON. No prose. No markdown. No code blocks.'
arm_usr = (
    f'Fix bug using CONSTRAINED actions.\n\n'
    f'RULES:\n1. Output ONLY JSON\n2. replacement_snippet must be minimal (1-3 lines)\n'
    f'3. Do NOT rewrite entire function\n4. If uncertain: {{"abstain": true}}\n\n'
    f'AVAILABLE: REPLACE_EXPR, CALL_EXISTING_HELPER, SET_REQUIRED_STATE_THEN_CALL, ABSTAIN\n\n'
    f'{evidence}\n\nCode:\n{anchor}\n\n'
    f'Output JSON: {{"action_type":"TYPE","replacement_snippet":"code","expected_effect":"what","confidence":0.0-1.0}}'
)
arm = ollama_gen('qwen2.5-coder:7b', arm_sys, arm_usr)
print(f'  {len(arm)} chars | JSON={ "{" in arm} | Cycle={"Cycle" in arm}')

print()
print('=== Uplift Summary ===')
print(f'  Bare:     {len(bare)} chars, markdown={chr(96)*3 in bare}, Cycle={"Cycle" in bare}')
print(f'  Evidence: {len(ev)} chars, markdown={chr(96)*3 in ev}, Cycle={"Cycle" in ev}')
print(f'  Constrain:{len(con)} chars, JSON={ "{" in con}, Cycle={"Cycle" in con}')
print(f'  Armor:    {len(arm)} chars, JSON={ "{" in arm}, Cycle={"Cycle" in arm}')

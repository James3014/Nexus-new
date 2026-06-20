# Nexus Model-Candidate Operator Runbook

**Date**: 2026-06-18
**Status**: INTERNAL USE ONLY

---

## Quick Start

### 1. Verify Environment
```bash
# Check Ollama
ollama list | grep qwen2.5-coder

# Check workspaces
ls .nexus/workspaces/

# Check Python
python3 --version
```

### 2. Run a Single Candidate Replay
```bash
cd /Users/jameschen/Workspace/nexus
python3 -c "
import sys; sys.path.insert(0, '.')
from nexus.patching.indentation_insertion import detect_indentation_intent
# ... (use scripts/strategy/s5_7_consolidation.py)
"
```

### 3. Run Strategy Tournament
```bash
python3 scripts/strategy/s2_diverse_strategy_rollout.py
```

### 4. Check Source Cleanliness
```bash
python3 -c "
# Check if buggy line exists in source
import subprocess
ws = '.nexus/workspaces/astropy'
subprocess.run(['git', 'checkout', '--', '.'], cwd=ws)
source = open(f'{ws}/target_file.py').read()
print('CLEAN' if 'buggy_line' in source else 'STALE')
"
```

## Common Issues

### Source-Stale Block
If source guard blocks a candidate:
1. Check if the bug was already patched
2. Use a different candidate from source-clean manifest
3. Do NOT bypass source guard

### Indentation Mismatch
If model output lacks leading whitespace:
1. Indentation normalization is applied automatically
2. Check base_indent from detect_indentation_intent()
3. Model output is projected into correct indentation context

### M0 Non-Deterministic
If fresh M0 fails to reproduce:
1. This is expected (nondeterministic local model)
2. Use stored-output (R0) replay for consolidation
3. Do NOT count as model failure

## Safety Rules

1. **NEVER** bypass source guard
2. **NEVER** count stored-output as fresh success
3. **NEVER** make public benchmark claims
4. **NEVER** export without human review
5. **ALWAYS** verify source hash before model-call
6. **ALWAYS** use indentation normalization
7. **ALWAYS** check parent-boundary preservation

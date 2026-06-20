# V6-B SCoRe-Like Correction Loop Design

## Status: V6B_SCORE_LOOP_DESIGN_READY

## 1. Why Offline SFT Alone May Fail

- **Distribution mismatch**: Static examples don't capture dynamic retry behavior
- **Behavior collapse**: Model may learn to always produce same output
- **Unnecessary modification**: Model may modify correct answers

## 2. Nexus Physical Feedback Sources

| Source | Signal |
|--------|--------|
| Verifier result | Pass/fail with exit code |
| Patch parser result | Format valid/invalid |
| Patch authority | VERBATIM/CANONICAL/CROSS_FILE/FUZZY |
| Compliance checker | Gate pass/fail |
| Env taxonomy | Blocker classification |
| Export classification | Bucket assignment |

## 3. Candidate Loop

```
Attempt 1 → Parser → Authority → Verifier → Compliance → Observation
    ↓ (if fail)
StructuredPacket → Retry Prompt → Attempt 2 → Parser → Verifier → Compliance → Final
```

## 4. Safety Constraints

- No training without owner approval
- No private code leakage
- No reward hacking (verifier is ground truth)
- No model success without verifier pass
- No env blocker as model failure

## 5. Minimal Future Experiment

**Format correction only**:
- Train on format-valid vs format-invalid pairs
- Use structured packet as reward signal
- Not full repair RL initially

## Recommendation

**V6B_SCORE_LOOP_DESIGN_READY** — design documented, no implementation until training approved.

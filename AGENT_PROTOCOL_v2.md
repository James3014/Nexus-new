# 🛡️ Nexus Agent Protocol v2 (Active)

## 🎯 Closeout Hard-Gate Requirement
**Completion claims are strictly forbidden unless `nexus:closeout` passes.**

Every task completion MUST be verified by running:
```bash
uv run scripts/engine/nexus_cli.py nexus:closeout --contract .nexus/reports/done_contract.json
```

The `done_contract.json` MUST contain:
- `linter_exit_code`: Must be 0
- `ci_gate_exit_code`: Must be 0
- `required_tests_passed`: Must be true
- `commit_sha`: Non-empty string
- `changed_files`: Non-empty list of paths

Failure to pass this gate blocks any "PASS" reporting or task finalization.

## 🔧 Gemini+Nexus Stable Invocation (Required for headless runs)
When invoking Gemini for implementation from automation/headless contexts, use:

```bash
python3 scripts/ops/gemini_nexus_invoke.py \
  --preflight \
  --prompt-file <task_prompt.md> \
  --report-file .nexus/reports/gemini_invoke_report.json
```

Why:
- prevents concurrent overlapping Gemini runs (single-flight lock)
- detects `AUTH_LOOP` early instead of hanging long tasks
- applies timeout + retry policy with explicit failure reason

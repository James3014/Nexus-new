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

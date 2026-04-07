# 🛡️ Nexus Closeout Enforcement Path

## 📌 Overview
To prevent premature PASS reporting and ensure all deliverables meet the required quality standards, Nexus now implements a **Closeout Hard-Gate**. This gate validates a "Done Contract" before any task can be officially closed.

## ⚙️ Enforcement Mechanism
The enforcement is handled via the `nexus:closeout` command, which invokes `scripts/ops/closeout_guard.py`.

### Command
```bash
uv run scripts/engine/nexus_cli.py nexus:closeout --contract <path_to_contract>
```

### Required Fields in `done_contract.json`
| Field | Requirement |
|-------|-------------|
| `linter_exit_code` | Must be `0` |
| `ci_gate_exit_code` | Must be `0` |
| `required_tests_passed` | Must be `True` |
| `commit_sha` | Must be a non-empty string |
| `changed_files` | Must be a non-empty list of paths |

## 🚫 Protocol Restriction
As per `AGENT_PROTOCOL_v2.md`, completion claims are **strictly forbidden** unless the `nexus:closeout` command returns a success status.

## 🛠️ Troubleshooting
If the gate fails, a machine-readable JSON report will be output to stdout detailing which checks failed. Ensure all local tests and CI checks are passing before attempting closeout.

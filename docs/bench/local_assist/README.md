# Local Assist bench assets

- `gate2_live_smoke_task.json` — bounded live smoke specification
- `tasks/` — paired experiment task set (3–5)
- `online_execution_policy.example.json` — copy to `.nexus/online_execution_policy.json` for workspace defaults

Runtime loads workspace Online policy from:

```text
.nexus/online_execution_policy.json
```

Default when missing: `deny` (conservative).

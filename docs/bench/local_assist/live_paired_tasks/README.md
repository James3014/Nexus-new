# Live paired tasks (R3)

Five distinct families for Arms A/B under `online_policy=require`.

Do **not** fill results with fixtures. Execute only when a registered Online provider is READY via Nexus discovery.

Product entry:

```bash
nexus run --task "<task_statement>" --local-assist-policy disabled --online-policy require   # Arm A
nexus run --task "<task_statement>" --local-assist-policy advisor  --online-policy require   # Arm B
```

Manifest copy also lives under campaign evidence `paired_manifest.json`.

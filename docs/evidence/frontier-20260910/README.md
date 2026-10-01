# Nexus frontier delivery archive — 2026-09-10

This directory preserves the completed #807, #850/#853, and #842 work and its regression evidence. These are immutable historical observations and test logs, not active runtime/control-plane state or fresh authority. Source, deployment, native acceptance and optional skips retain their original separate claim boundaries.

The Owner subsequently requested all deliverables be committed and merged and temporary workspaces cleaned. This delivery carries the accepted r28 test delta into current main under that new instruction; it does not rewrite the earlier acceptance receipt, which correctly said the canary Candidate was unmerged at the time. The test is a historical canary fixture, not proof of current mount health. The full runtime Git history is not merged.

- `frontier-audit/controller-closeout.md`: controller closeout and explicit residual/claim limits.
- `frontier-audit/current-completion-matrix.{json,csv,md}`: layer-specific evidence.
- `frontier-audit/frontier-evidence-qualification.json`: exact frozen revisions, commands, logs and skip reasons.
- `project-entry/`: original implementation, runtime, native-entry and recovery evidence; superseded observations remain historical.
- `artifact-manifest.json`: original paths, archived paths and archived SHA-256 (the CSV and four logs have whitespace normalization with both hashes recorded). Historical scripts use `.py.txt` to prevent accidental execution or collection as project source.

Two rollback Git bundles remain in the durable local evidence folder. Their hashes are included in the manifest; they are rollback backups, not source deliverables. No secret material or live writable authority state is installed by this archive. Paths to temporary verification worktrees are historical provenance and may no longer exist after cleanup; their logs, revisions and hashes remain archived here.

No release, production or future job authorization is claimed. Historical UNKNOWN attempts remain preserved and must not be blindly resent.

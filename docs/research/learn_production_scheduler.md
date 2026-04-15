# Learn Production Scheduler

This runbook wires Learn refresh into macOS `launchd` so refresh and benchmark curation can run without manual intervention.

## Install (dry-run first)

```bash
uv run python scripts/ops/learn_refresh_launchd.py install \
  --dry-run \
  --topic openharness \
  --interval-sec 1800 \
  --benchmark-manifest docs/research/learn_benchmark_curated.json
```

## Install (real)

```bash
uv run python scripts/ops/learn_refresh_launchd.py install \
  --topic openharness \
  --interval-sec 1800 \
  --benchmark-manifest docs/research/learn_benchmark_curated.json
```

## Status

```bash
uv run python scripts/ops/learn_refresh_launchd.py status
```

## Uninstall

```bash
uv run python scripts/ops/learn_refresh_launchd.py uninstall
```

## Question Bank Governance

1. Collect candidate questions from real failures (`UNKNOWN`/`CONFLICT`) in `learn_benchmark_candidates.jsonl`.
2. Curate benchmark set:

```bash
uv run scripts/engine/nexus_cli.py nexus learn:benchmark-curate \
  --topic openharness \
  --max-questions 40 \
  --manifest-file docs/research/learn_benchmark_curated.json
```

3. Run benchmark with curated manifest:

```bash
uv run scripts/engine/nexus_cli.py nexus learn:benchmark \
  --manifest-file docs/research/learn_benchmark_curated.json \
  --topic openharness
```


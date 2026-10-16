# F-08B Core Dependency Caps

**Status:** `F08B_CORE_DEPENDENCY_CAPS_ADDED`

**Date:** 2026-06-29

## Summary

Added conservative upper bounds to 14 low-risk core dependencies.

## Dependencies Capped

| Package | Before | After |
|---|---|---|
| pydantic | >=2.0 | >=2.0,<3.0 |
| PyYAML | >=6.0 | >=6.0,<7.0 |
| pandas | >=2.0.0 | >=2.0.0,<3.0.0 |
| requests | >=2.31.0 | >=2.31.0,<3.0.0 |
| filelock | >=3.0.0 | >=3.0.0,<4.0.0 |
| rich | >=13.0.0 | >=13.0.0,<14.0.0 |
| networkx | >=3.0 | >=3.0,<4.0 |
| anyio | >=4.0.0 | >=4.0.0,<5.0.0 |
| typer | >=0.9.0 | >=0.9.0,<1.0.0 |
| click | >=8.1.0 | >=8.1.0,<9.0.0 |
| tqdm | >=4.65.0 | >=4.65.0,<5.0.0 |
| opentelemetry-api | >=1.15.0 | >=1.15.0,<2.0.0 |
| opentelemetry-sdk | >=1.15.0 | >=1.15.0,<2.0.0 |
| rank-bm25 | >=0.2.2 | >=0.2.2,<1.0.0 |

## Commands Run

```bash
uv sync --all-groups --all-extras
uv run pyright nexus/core
uv run bandit -r nexus/core -ll -ii
```

## Results

| Metric | Before | After |
|---|---|---|
| Pyright errors | 0 | 0 |
| Bandit medium/high | 0 | 0 |

## Scope Statement

- Only low-risk core dependencies capped
- ML/browser/web3 deps not touched
- 14 dependency lines changed

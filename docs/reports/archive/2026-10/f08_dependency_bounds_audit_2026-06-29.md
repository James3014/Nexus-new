# F-08A Dependency Bounds Audit

**Status:** `F08A_DEPENDENCY_BOUNDS_AUDIT`

**Date:** 2026-06-29

## Summary

Inventory of 41 dependency specs lacking upper bounds in `pyproject.toml`.

## By Section

### project.dependencies (20)

| Package | Spec | Classification |
|---|---|---|
| pydantic | >=2.0 | low-risk to cap |
| PyYAML | >=6.0 | low-risk to cap |
| lancedb | >=0.4.0 | needs ecosystem judgment |
| pandas | >=2.0.0 | low-risk to cap |
| requests | >=2.31.0 | low-risk to cap |
| filelock | >=3.0.0 | low-risk to cap |
| grpcio | >=1.50.0 | needs ecosystem judgment |
| grpcio-tools | >=1.50.0 | needs ecosystem judgment |
| protobuf | >=4.21.0 | needs ecosystem judgment |
| rich | >=13.0.0 | low-risk to cap |
| networkx | >=3.0 | low-risk to cap |
| anyio | >=4.0.0 | low-risk to cap |
| aiohttp | >=3.8.0 | low-risk to cap |
| httpx | >=0.24.0 | needs ecosystem judgment |
| typer | >=0.9.0 | low-risk to cap |
| click | >=8.1.0 | low-risk to cap |
| websockets | >=11.0 | needs ecosystem judgment |
| tqdm | >=4.65.0 | low-risk to cap |
| opentelemetry-api | >=1.15.0 | low-risk to cap |
| opentelemetry-sdk | >=1.15.0 | low-risk to cap |
| rank-bm25 | >=0.2.2 | low-risk to cap |
| datasets | >=5.0.0 | needs ecosystem judgment |

### optional-dependencies.ml (10)

| Package | Spec | Classification |
|---|---|---|
| torch | >=2.0.0 | dev-only lower priority |
| transformers | >=4.30.0 | dev-only lower priority |
| sentence-transformers | >=2.2.0 | dev-only lower priority |
| huggingface-hub | >=0.16.0 | dev-only lower priority |
| safetensors | >=0.3.0 | dev-only lower priority |
| accelerate | >=0.21.0 | dev-only lower priority |
| scikit-learn | >=1.2.0 | dev-only lower priority |
| scipy | >=1.10.0 | dev-only lower priority |
| fsspec | >=2023.6.0 | dev-only lower priority |

### optional-dependencies.browser (1)

| Package | Spec | Classification |
|---|---|---|
| playwright | >=1.58.0 | dev-only lower priority |

### optional-dependencies.web3 (1)

| Package | Spec | Classification |
|---|---|---|
| web3 | >=6.0.0 | dev-only lower priority |

### dependency-groups.dev (6)

| Package | Spec | Classification |
|---|---|---|
| pytest | >=9.0.3 | dev-only lower priority |
| pytest-asyncio | >=0.23.0 | dev-only lower priority |
| pytest-timeout | >=2.3.1 | dev-only lower priority |
| ruff | >=0.4.0 | dev-only lower priority |
| pyright | >=1.1.370 | dev-only lower priority |
| bandit | >=1.7.0 | dev-only lower priority |

### build-system (1)

| Package | Spec | Classification |
|---|---|---|
| poetry-core | >=1.0.0 | dev-only lower priority |

## Summary by Classification

| Classification | Count |
|---|---|
| low-risk to cap | 14 |
| needs ecosystem judgment | 7 |
| dev-only lower priority | 18 |
| optional (ml/browser/web3) | 12 |

## Commands Run

```bash
rg -n '>=' pyproject.toml
rg -c '>=' pyproject.toml
```

## Scope Statement

- Audit only, no dependency changes
- Identified 14 low-risk candidates for F-08B

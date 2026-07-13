---
title: Claim Taxonomy
type: normative
status: active
lifecycle: current
authority: normative
owner: nexus-core
verified_at: '2026-07-13'
verified_against_commit: 957cd19c744d168ff050667b611adca5fb20d56f
source_of_truth: repository evidence and current runtime reports
confidence: high
---

# Claim Taxonomy

This page defines evidence thresholds for every claim level in Nexus. No claim may be made at a level higher than the available evidence supports.

## Mandatory distinctions

These inequalities are absolute:

- `UNIT_VERIFIED` != `INTEGRATED`
- `INTEGRATED` != `RUNTIME_INVOKED`
- `RUNTIME_INVOKED` != `LIVE_SOLVED`
- `BENCHMARK_VERIFIED` != `PRODUCT_RUNTIME`
- `PRODUCT_RUNTIME` != `PRODUCTION_READY`
- `PRODUCTION_READY` != `PUBLIC_CLAIM_ALLOWED`

## Claim levels

### DOCUMENTED

| Field | Value |
|-------|-------|
| **Definition** | A description exists in documentation or code comments |
| **Minimum evidence** | A Wiki page or code comment describes the capability |
| **What it does not prove** | That the code exists, works, or has been tested |
| **Allowed wording** | "Documented", "described in [page]" |
| **Forbidden wording** | "Exists", "implemented", "working", "complete" |

### EXISTS

| Field | Value |
|-------|-------|
| **Definition** | A file, class, or function with the claimed name exists in the repository |
| **Minimum evidence** | File existence check (`test -f`, `ls`, glob) |
| **What it does not prove** | That the code is correct, tested, or used by anything |
| **Allowed wording** | "Exists in [path]", "file [name] is present" |
| **Forbidden wording** | "Implemented", "working", "functional", "complete" |

### UNIT_VERIFIED

| Field | Value |
|-------|-------|
| **Definition** | The code has at least one passing unit test |
| **Minimum evidence** | `pytest` pass on the specific test file |
| **What it does not prove** | Integration with other components, runtime behavior, or correctness in production context |
| **Allowed wording** | "Unit tested", "pytest passing for [test]" |
| **Forbidden wording** | "Integrated", "working in runtime", "production ready", "complete" |

### CONTRACT_VERIFIED

| Field | Value |
|-------|-------|
| **Definition** | The code passes contract tests that verify interface compatibility |
| **Minimum evidence** | Contract test suite pass, schema compatibility check |
| **What it does not prove** | Runtime invocation, end-to-end behavior, or production readiness |
| **Allowed wording** | "Contract verified", "interface compatible" |
| **Forbidden wording** | "Integrated", "runtime proven", "production ready" |

### INTEGRATED

| Field | Value |
|-------|-------|
| **Definition** | The component is wired into a larger system and the wiring has been tested |
| **Minimum evidence** | Integration test showing the component called within its parent system |
| **What it does not prove** | Runtime behavior under real load, production readiness, or end-to-end correctness |
| **Allowed wording** | "Integrated into [system]", "wired into [component]" |
| **Forbidden wording** | "Runtime proven", "production ready", "live", "complete" |

### RUNTIME_INVOKED

| Field | Value |
|-------|-------|
| **Definition** | The code has been invoked in a real runtime context (not a test harness) |
| **Minimum evidence** | Runtime log, receipt, or trace showing invocation |
| **What it does not prove** | Correctness of outcome, production readiness, or user-facing reliability |
| **Allowed wording** | "Runtime invoked", "executed in [context]" |
| **Forbidden wording** | "Production ready", "live solved", "complete", "sealed" |

### LIVE_SOLVED

| Field | Value |
|-------|-------|
| **Definition** | The code has produced a correct outcome in a live or production-like context |
| **Minimum evidence** | Runtime receipt with verified outcome, user-confirmed result |
| **What it does not prove** | Scalability, reliability under load, or production readiness |
| **Allowed wording** | "Live solved in [context]" |
| **Forbidden wording** | "Production ready", "complete", "sealed", "public claim allowed" |

### BENCHMARK_VERIFIED

| Field | Value |
|-------|-------|
| **Definition** | The capability has been measured in a benchmark harness with reproducible results |
| **Minimum evidence** | Benchmark run with recorded metrics, methodology, and scope |
| **What it does not prove** | Product runtime performance, production readiness, or real-world behavior |
| **Allowed wording** | "Benchmark verified", "measured in [harness] with [scope]" |
| **Forbidden wording** | "Product runtime", "production ready", "public claim allowed" |

### BENCHMARK_UPLIFT_OBSERVED

| Field | Value |
|-------|-------|
| **Definition** | A benchmark comparison shows measurable improvement in the treatment arm |
| **Minimum evidence** | A/B comparison with labeled baseline and treatment, per-task deltas |
| **What it does not prove** | That the uplift applies to product runtime, different models, or different task distributions |
| **Allowed wording** | "Uplift of [X]pp observed on [suite] with [model]" |
| **Forbidden wording** | "Product runtime uplift", "production improvement", "public claim allowed" |

### PRODUCT_RUNTIME

| Field | Value |
|-------|-------|
| **Definition** | The capability functions in the actual product runtime, not just a benchmark or test harness |
| **Minimum evidence** | End-to-end runtime trace in the product execution path with verified outcome |
| **What it does not prove** | Production readiness, scalability, or public claim eligibility |
| **Allowed wording** | "Product runtime verified", "functions in [runtime path]" |
| **Forbidden wording** | "Production ready", "complete", "sealed", "public claim allowed" |

### PRODUCTION_READY

| Field | Value |
|-------|-------|
| **Definition** | The capability meets all reliability, security, and operational requirements for production deployment |
| **Minimum evidence** | Production readiness checklist pass, security audit, load testing, monitoring in place |
| **What it does not prove** | Public claim eligibility (may require legal, marketing, or external review) |
| **Allowed wording** | "Production ready", "deployment ready" |
| **Forbidden wording** | "Public claim allowed", "market ready" |

### PUBLIC_CLAIM_ALLOWED

| Field | Value |
|-------|-------|
| **Definition** | The claim has been reviewed and approved for external public communication |
| **Minimum evidence** | Explicit approval from governance authority, claim review pass |
| **What it does not prove** | That the claim is true in all contexts (always qualify with scope, model, suite) |
| **Allowed wording** | "Public claim approved for [scope]" |
| **Forbidden wording** | Any unqualified superlative ("world's first", "best in class") |

## Prohibited phrases

The following phrases are prohibited unless the corresponding evidence level is met:

| Phrase | Minimum required level |
|--------|----------------------|
| "complete" | PRODUCTION_READY |
| "sealed" | PRODUCTION_READY |
| "productized" | PRODUCT_RUNTIME |
| "production" (as adjective for Nexus itself) | PRODUCTION_READY |
| "ready" (unqualified) | PRODUCTION_READY |
| "public claim allowed" | PUBLIC_CLAIM_ALLOWED |
| "fully integrated" | INTEGRATED (with specific system named) |
| "fully production ready" | PRODUCTION_READY |

## Usage guidance

When writing claims in documentation, code comments, or reports:

1. State the evidence level explicitly or use only wording permitted at that level.
2. Always name the specific evidence (file, test, run ID, log).
3. Always state the scope (which model, which suite, which context).
4. Never use a claim level as a substitute for evidence.

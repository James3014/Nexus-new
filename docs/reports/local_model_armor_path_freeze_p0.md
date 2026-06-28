# Local Model Armor: Path Freeze (P0)

## 1. The Four-Path Model Definition

The local model integration is structured across four distinct execution paths:

- **Path A**: `CapabilityPlanner` / `capability_ab_runner.py` / `with_nexus` mainline integration. Holds the official routing truth.
- **Path B**: `LocalHeal` / Qwen / Ollama local repair pipeline.
- **Path C**: H5-H8 Local-to-Capability bridge (`hybrid_route.py` and `capability_adapter.py`).
- **Path D**: Isolated diagnostic and probe scripts.

---

## 2. Classification of Path D

The diagnostic-only execution scope (Path D) specifically includes:

- `scripts/local_heal/run_june_regression_pack.py`
- `scripts/local_heal/run_real_qwen_small_batch_eval.py`
- `real_model_probe` / `FakePhase` artifacts
- Isolated memory evaluation scripts

---

## 3. Allowed Usage of Path D

Path D may be utilized exclusively for:
- Ad-hoc diagnostics
- Local regression replays
- Basic local model output/patch validation and probing

---

## 4. Forbidden Claims for Path D

Path D must **never** be cited or referenced as:
- A-side integration evidence
- `CapabilityPlanner` mainline evidence
- `with_nexus` evidence
- Public benchmark evidence
- Production readiness evidence
- Evidence of Qwen solving SWE-bench problems in production

---

## 5. Evidence Decision Table

| Evidence Source | Allowed Claim |
|---|---|
| Path A `with_nexus` row/evidence bundle | A-side route evidence |
| Path B `LocalHeal` receipt | Local repair pipeline evidence |
| Path C hybrid route decision / adapter row | Bridge/contract safety evidence |
| Path D probe | Diagnostic-only evidence |

---
**Status**: ACTIVE & FROZEN (Path D is diagnostic-only. Path A remains the route truth source.)

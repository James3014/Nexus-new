# Local Model Sprint A3.1: HealPipeline.run Invocation Truth Check

**Status:** A3_1_HEALPIPELINE_RUN_INVOCATION_TRUTH_COMPLETE
**Date:** 2026-07-01

## Key Finding

**HealPipeline.run() is NEVER called by the bridge.**

The bridge (`LocalHealPipelineCapabilityExecutor.execute`) does:
1. ✅ Instantiates `HealPipeline(ollama_generate_fn=_provider_generate)` — line 341
2. ✅ Appends `"heal_pipeline"` to `invoked_modules` — line 346
3. ✅ Sets `path_a_actual_execution = True` — line 347
4. ❌ **Does NOT call `pipeline.run()`** — no `.run()` call anywhere in the bridge

The only `.run()` call in `local_model_capability_executors.py` is at line 99, in a different class (`DDTreeLocalExecutor`), not in the bridge.

## A3 Report Overclaim

A3 report stated:
> "Bridge to Existing HealPipeline.run"

This is inaccurate. The correct statement is:
> "Bridge instantiates HealPipeline with real provider wrapper, but does NOT call .run()"

## Telemetry Misleading

`localheal_pipeline_actual_execution=True` currently means "instantiation happened", NOT "pipeline execution happened". This is semantically misleading.

## What Exists vs What's Missing

| Component | Status |
|-----------|--------|
| HealPipeline instantiation | ✅ Done (with real provider) |
| HealPipeline.run() call | ❌ NOT DONE |
| Orchestrator.run() call | ❌ NOT DONE |
| Pipeline retry loop | ❌ NOT DONE |
| Pipeline verification loop | ❌ NOT DONE |
| Orchestrator repair loop | ❌ NOT DONE |

## Implications

1. A3's "bridge wired" claim is **PARTIAL** — instantiation only, no execution
2. A5's retry metadata is observational — no actual retry loop exists
3. The `localheal_pipeline` topology runs the model call directly through `provider.generate()`, then returns. The pipeline's 5-phase orchestration + orchestrator repair loop is never invoked.
4. Next step must wire `pipeline.run()` call, not just retry metadata

## Explicit Statements

- HealPipeline.run() is NOT called
- Orchestrator.run() is NOT called
- current A3 report overclaims
- localheal_pipeline_actual_execution means instantiation, NOT actual run
- No retry loop exists in bridge path

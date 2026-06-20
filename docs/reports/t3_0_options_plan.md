# T3.0 Options Plan

**Based on**: T2.9 GREEN (20/20 PASS)
**Date**: 2026-06-18

## T3 Gate Decision

T2.9 Verdict: **GREEN** — T3 is ALLOWED to start.

## Options

### Option A — T3.0 30-Task Attribution-Safe Diagnostic

- **Scope**: Expand from 20 to 30 tasks
- **Type**: Internal, same no-public-claim rules
- **Purpose**: Coverage breadth
- **Pros**: Broader failure class coverage, more regression anchors
- **Cons**: Still model_calls=0, doesn't advance model patch synthesis
- **Best if**: User wants more coverage before model-call experiments

### Option B — T3.0 Model-Call Reintroduction Experiment (RECOMMENDED)

- **Scope**: Controlled subset of 5-8 tasks
- **Type**: Internal, allow model_calls>0 on selected tasks
- **Purpose**: Distinguish model patch reward from deterministic recovery
- **Pros**: Advances toward real model patch synthesis, stronger for future S2T/training
- **Cons**: Requires model authority setup, higher complexity
- **Best if**: Clean replay evidence is strong and bootstrap is reproducible (✓ confirmed)

### Option C — T3.0 Clean-Room Workspace Reproducibility Audit

- **Scope**: Rebuild workspaces from bootstrap, replay 20-task set from scratch
- **Type**: Internal, hermetic isolation
- **Purpose**: Strongest trust and portability evidence
- **Pros**: Eliminates sys.path.insert hacks, proves true reproducibility
- **Cons**: Heavy lift, may surface dependency issues
- **Best if**: Clean replay has environment fragility (current replay is clean, so lower priority)

## Recommendation

**Option B** — T2.9 clean replay evidence is strong (20/20, all guards pass, bootstrap reproducible). The next logical step is to introduce controlled model_calls>0 on a subset to start distinguishing model patch reward from deterministic recovery.

T3.0 execution requires explicit user request. Not performed in T2.9.

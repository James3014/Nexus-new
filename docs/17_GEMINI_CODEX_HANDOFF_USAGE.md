# Gemini + Codex Handoff Usage (Current Nexus)

## Purpose

This guide defines the runnable workflow for current Nexus:

- Gemini CLI is the implementation actor.
- Codex-loop is the review and escalation gate.
- Nexus exports both human-readable and machine-readable next-step handoff.

## Core Outputs

After `codex_loop_brain.py` runs, it now exports:

- `/tmp/codex_loop_report.md`
- `/tmp/codex_next_action.json`

The JSON sidecar is the handoff contract for Gemini runners.

## CLI Entry Points

### 1) Run codex-loop normally

```bash
scripts/codex-loop.sh --mode audit README.md
```

### 2) Run codex-loop and emit Gemini handoff prompt

```bash
scripts/codex-loop.sh --mode audit README.md --emit-gemini-handoff
```

Default prompt output:

- `/tmp/gemini_handoff_prompt.txt`

### 3) Emit handoff prompt only (no new review run)

```bash
scripts/codex-loop.sh --handoff-only --emit-gemini-handoff
```

This consumes:

- `/tmp/codex_next_action.json`

### 4) Custom output path

```bash
scripts/codex-loop.sh --handoff-only --emit-gemini-handoff --handoff-output /tmp/gemini_task.txt
```

## Flags Added to `scripts/codex-loop.sh`

- `--emit-gemini-handoff`
- `--handoff-only`
- `--handoff-output <path>`

All other arguments are passed through to `codex_loop_brain.py`.

## Adapter Script

`scripts/core/gemini_handoff.py` converts handoff JSON to a Gemini-ready prompt.

Example:

```bash
python3 scripts/core/gemini_handoff.py --input /tmp/codex_next_action.json --output /tmp/gemini_task.txt
```

If input is missing, the script exits with code `2` and prints a clear error.

## Recommended Execution Loop

```text
Gemini edits
  -> codex-loop review
     -> next_action JSON
        -> gemini_handoff prompt
           -> Gemini next round
```

## Agent Rules

1. Use `/tmp/codex_next_action.json` as the machine source of truth for next-step decisions.
2. Use `/tmp/codex_loop_report.md` for human-readable context.
3. Do not regenerate intent manually when `next_action` already exists.
4. If `next_action=codex_patch`, escalate instead of repeating Gemini-only retries.
5. If `next_action=felo_research`, collect external facts before editing code again.

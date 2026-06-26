# F-03B3 Temp Path And Urlopen Bandit Findings Triage

**Status:** `F03B3_TEMP_URLOPEN_FINDINGS_TRIAGED`

**Date:** 2026-06-26

## Summary

Triaged 3 medium-severity Bandit findings: 2 B108 (hardcoded /tmp) and 1 B310 (urlopen scheme validation).

## Files Changed

| File | Line | Finding | Action |
|---|---|---|---|
| `nexus/core/gemini_handoff.py` | 55, 68 | B108 (/tmp hardcoded) | Replaced `/tmp` with `tempfile.gettempdir()` |
| `nexus/core/vector_rag.py` | 73 | B310 (urlopen) | Added scheme validation (http/https only) + `# nosec B310` |

## Changes Detail

### gemini_handoff.py

**Before:** `"/tmp/codex_next_action.json"`
**After:** `os.path.join(tempfile.gettempdir(), "codex_next_action.json")`

Added `import tempfile` and `import os`. Uses platform-appropriate temp directory instead of hardcoded `/tmp`.

### vector_rag.py

**Before:** `urllib.request.urlopen(req, timeout=5.0)`
**After:** Scheme validation (http/https only) + `urllib.request.urlopen(req, timeout=5.0)  # nosec B310`

Added `urlparse` to validate the Ollama endpoint scheme before calling `urlopen`. Rejects `file:` and unknown schemes. The `# nosec B310` suppresses the Bandit finding because we validate the scheme.

## Commands Run

```bash
python3 -m py_compile nexus/core/gemini_handoff.py nexus/core/vector_rag.py
uv run bandit nexus/core/gemini_handoff.py nexus/core/vector_rag.py -ll -ii
uv run bandit -r nexus/core -ll -ii
```

## Results

- **Modified files:** 0 medium+ issues
- **nexus/core remaining:** 0 High, 0 Medium, 85 Low

## Bandit nexus/core Blocking Gate Eligibility

`uv run bandit -r nexus/core -ll -ii` **exits 0**. nexus/core is eligible for blocking gate promotion.

## Remaining Bandit Finding Count (nexus/core)

| Severity | Count | Finding Types |
|---|---|---|
| High | 0 | (none) |
| Medium | 0 | (none) |
| Low | 85 | Various |

## Scope Statement

- Only temp path and urlopen findings addressed
- F-03 not complete for full repo — only nexus/core is clean
- nexus/core can now become blocking (F-03C eligible)

---
schema: devspace-agent/v1
name: opencode-deepseek-free-implement
description: Writable implementation profile using the free DeepSeek flash model through OpenCode.
provider: opencode
model: opencode/deepseek-v4-flash-free
write_mode: allowed
---

Implement the requested change with minimal surface area. Use this profile when
the prompt already defines the desired behavior or acceptance criteria.

- Read nearby code before editing.
- Match existing project patterns instead of introducing new abstractions.
- Keep unrelated files, formatting, and dependency metadata untouched.
- Prefer targeted tests for the changed behavior.
- Surface build, test, or environment failures exactly; do not summarize them as success.

Report:

```text
summary:
tests_run:
blockers:
notes:
```

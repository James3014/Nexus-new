# Task Card: astra-native-context-stdio-20260907

artifact_authority: current
task_id: `astra-native-context-stdio-20260907`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Implement one narrow Context-only stdio MCP adapter host for the accepted ContextContinuityService artifact. Use real MCP JSON-RPC initialize/tools/list/tools/call framing, not the fixture bridge protocol. Exactly four public context tools: checkpoint/resume/search/read_item. Internal host capture is not a public authority or arbitrary ingestion tool. Server binds OS/local launcher principal, exact root/scope, session/process identity and AccessPolicy before requests. Capture only NEXUS_RECORDED visible tool I/O; no hidden reasoning/full native history claim. Reject caller auth/root/policy/route/worker/effect fields; ACL before existence, strict DTOs, bounded frames/reads/timeouts, replay/conflict, TTL/tamper/stale historical exact read, echo exclusion. Evidence/tracer binds raw tool calls and stable IDs/digests/revision and WORKING_CONTEXT_NON_AUTHORITATIVE. Preserve all lifecycle behavior by keeping this host separate; never instantiate a second lifecycle Controller. Base4887d8f6a3faf50d6b600f2c170526e08d4bf408 plus exact coordinator-transported card/index. Use accepted Context wheel as explicit dependency; no legacy-source fallback or recopy of independent owner implementation. Prepare opt-in native acceptance harness for two real Codex CLI sessions with distinct IDs and MCP processes; checkpoint hint omits secret detail only in captured raw tool I/O, B resumes/searches/reads exact bytes after A closes and after restart. Native calls are NOT part of default unit tests. No model calls before independent root source review. No API key/SDK/Agy calls; eventual native calls use verified ChatGPT-login Codex CLI and per-invocation config, without changing CODEX_HOME/auth/global config. Local temporary fixture roots only. This card grants source implementation/scoped commit, not local lifecycle Candidate, admission, merge, deployment, production auth or native PASS. Independent root physical diff/tests and actual native witness required.

## Allowed files

- `nexus_context_stdio/pyproject.toml`
- `nexus_context_stdio/__init__.py`
- `nexus_context_stdio/protocol.py`
- `nexus_context_stdio/host.py`
- `nexus_context_stdio/capture.py`
- `nexus_context_stdio/server.py`
- `tests/nexus_context_stdio/test_protocol_and_host.py`
- `tests/nexus_context_stdio/test_two_codex_sessions.py`
- `tests/nexus_context_stdio/test_negative_and_restart.py`

## Verification commands

```bash
python3 -m pytest tests/nexus_context_stdio/test_protocol_and_host.py tests/nexus_context_stdio/test_negative_and_restart.py -q
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

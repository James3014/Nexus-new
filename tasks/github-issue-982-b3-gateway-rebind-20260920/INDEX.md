# Campaign Index: github-issue-982-b3-gateway-rebind-20260920

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Converge the live ChatGPT-facing Nexus Gateway from its currently loaded c6e2609f lineage to exact GitHub main 45cca97712b8801c3c0bf543bec8984ea5cf3104 / tree 0b40ad95b433a15f2ab140ec64fe312a53c7d66a, which contains the merged #1032 MiMo route and valid #982 B3 R1-B contract. Reuse only the existing #526 durable recovery manager and previously accepted manager/runtime lineage. Authorize only a fresh tracked recovery-authority receipt at the existing fixed path. No production/runtime source code change, no new manager/process authority, no manual launchctl/plist/PID manipulation, no provider canary, no G4. The host effect may start only after the exact authority receipt is independently verified, merged, materialized byte-identically, and the typed DevSpace recovery preflight returns effectStarted=false with TARGET_READY and ROLLBACK_READY. AUTO_CHAIN=false.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `issue-982-b3-gateway-rebind-20260920` | `00-issue-982-b3-gateway-rebind-20260920.md` | ACTIVE | Owner confirmation |

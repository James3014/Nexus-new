---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR: Fail closed on remote HealingArtifact ingress

## Status

Accepted

## Context

Remote registry sync accepted generic event payloads and published them after adding remote metadata. That was acceptable for low-risk telemetry, but not for `healing_artifact_announced`, because healing packets carry cross-node repair advice and must be treated as hostile input at the mTLS boundary.

The TDD red run exposed two concrete gaps:

- `artifact_from_packet()` rejected production writes but did not reject mutating `allowed_actions`.
- `RegistryMessageHandler._handle_event()` published remote healing artifacts without packet, signature, or key-policy validation.

## Decision

Remote healing ingress now fails closed:

- Healing packets must advertise exactly `["observe", "report"]` as allowed actions.
- Remote `healing_artifact_announced` events are validated through a transport receipt before publishing.
- Invalid packets return `status=error` with a receipt and are not published.
- Valid packets publish a sanitized payload derived from the verified artifact, not from caller-supplied spoofable fields.

## Consequences

Cross-node healing can be audited without allowing remote nodes to smuggle mutating repair instructions. Socket callers get a receipt readback that can be persisted in reports or route receipts.

## Lesson

Do not reuse a generic remote event ingress for security-sensitive semantic events. The boundary adapter must validate the domain contract before publishing.

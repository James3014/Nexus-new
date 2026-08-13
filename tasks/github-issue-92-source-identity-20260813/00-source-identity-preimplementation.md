---
artifact_authority: current
owner: James Chen
status: blocked_serialize_after_issue_29
purpose: Freeze Issue #92 physical source identity semantics without preempting Issue #29 runtime ownership.
baseline: f3dc8d28a0f90d5c5fd2f31dbeb0ab2f29f7ca04
issue: 92
allowed_files:
  - tasks/github-issue-92-source-identity-20260813/INDEX.md
  - tasks/github-issue-92-source-identity-20260813/00-source-identity-preimplementation.md
max_files: 2
auto_chain: false
---

# Issue #92 — Physical source identity preimplementation gate

## Objective

Compile the settled Issue #92 contract while implementation remains serialized
behind Issue #29. A later implementation must validate an optional declared
source assertion against bytes read from a runtime-owned trusted workspace root
before evidence construction or provider invocation.

## Current source evidence

- `UnifiedRuntimeRequest` has no declared physical-source identity field.
- The current evidence bundle `source_hash` is synthetic request metadata:
  `sha256(workspace_revision + ":" + task_statement)`.
- `nexus/services/capability_evidence_bundle.py` owns canonical bundle hashing
  and verification; Issue #92 must not overwrite or relabel that hash.
- `CapabilityPlanner` remains the sole route/capability selector and is not the
  physical-byte authority.

## Dependency and overlap

- Hard mutation fence: `SERIALIZE_AFTER:#29`.
- Issue #29 owns the moving `unified_runtime.py` same-task Local-to-Online
  evidence and receipt-identity surfaces.
- Issue #49 is independently `SERIALIZE_AFTER:#29`; Issue #92 must not absorb
  its final-delivery claim enforcement.
- Open-PR readback at compilation found no current PR changing the prospective
  Issue #92 runtime paths, but this does not override the semantic #29 fence.

## Frozen semantics for the later implementation

1. The caller may supply an optional declaration containing a normalized
   repository-relative regular-file path and an expected lowercase SHA-256.
2. The declaration cannot select its own root. Runtime supplies the trusted
   workspace root and reads the physical bytes.
3. Missing declarations preserve current behavior. A supplied malformed,
   missing, stale, substituted, escaped, symlinked, non-regular, or mismatched
   source fails before evidence or provider calls.
4. Runtime binds task, workspace revision, generated attempt, path, bytes,
   digest, and stable file identity. Caller/planner prose cannot manufacture
   physical truth.
5. The bound physical digest is separate from the existing canonical evidence
   bundle `source_hash`; neither that field nor `bundle_hash` may be replaced.
6. No second Router, Planner, verifier, claim authority, lifecycle authority,
   or Workforce selector may be created.

## Hostile verification required after rebind

- exact regular file and digest passes;
- digest mismatch, byte tamper, missing file/root, malformed digest, absolute
  path, `..` escape, root/file symlink, directory, and unreadable source fail
  closed with zero provider calls;
- rename/substitution/inode drift between validation and use fails closed;
- stale task/workspace/attempt bindings and cross-task declarations fail;
- omitted declaration preserves legacy behavior;
- declared physical digest cannot overwrite canonical bundle source identity;
- route, Workforce admission, finding/claim, and final-delivery authority remain
  unchanged.

## Allowed files now

Only this card and its `INDEX.md`. No product or test file is authorized before
the post-#29 rebind.

## Forbidden scope

- product and test mutation;
- `nexus/services/unified_runtime.py` or `CapabilityPlanner` changes now;
- `capability_evidence_bundle.py` hash migration;
- Issue #29 same-task consumption or Issue #49 final delivery;
- route, Workforce, lifecycle, approval, integration, merge, release, runtime
  activation, #191, or #143;
- Task Card self-widening or successor activation.

## Verification

- exact two-file changed-path audit;
- `git diff --check`;
- read back the committed card blob/hash;
- confirm `AUTO_CHAIN=false` and status remains blocked.

## Exit

This card exits only as `TASK_CARD_COMPILED_IMPLEMENTATION_NOT_AUTHORIZED`.
After #29 physically settles, the primary coordinator must create a fresh
Owner-authorized implementation frontier with exact current blobs, files,
tests, overlap, and claim ceiling. This card cannot authorize that mutation.

## Block class

`RECOVERABLE_BLOCK — SERIALIZE_AFTER_ISSUE_29`

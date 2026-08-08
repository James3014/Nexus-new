# Nexus OpenWiki Implementation-Wiki Contract

authority: derived_non_authoritative

## Purpose

This OpenWiki is a repository-derived implementation observation layer.

It may help engineers understand code structure, current implementation evidence, wiring evidence, runtime surfaces, and implementation drift.

It is not a Nexus source of governance authority, route authority, approval authority, integration authority, release authority, production truth, or governed-Wiki truth.

## Authority ceiling

`AGENTS.md` remains repository/agent authority.

CapabilityPlanner and HybridRouteDecision remain Nexus route authority.

OpenWiki must not create, infer, promote, or duplicate route authority.

`nexus_wiki_vault/` is governed separately and must not be modified or treated as generated OpenWiki output.

Generated OpenWiki material is always `derived_non_authoritative`.

Do not claim production readiness, release readiness, public claimability, approval, integration, or canonical governance status from OpenWiki evidence.

## Required V3 classification

For every material claim about a subsystem, service, engine, router, executable, workflow, capability, adapter, or runtime component, keep these axes separate:

* `implementation_status`
* `wiring_status`
* `runtime_surfaces`
* `authority_roles`
* `evidence_basis`
* `claim_ceiling`

Use a structure equivalent to:

```yaml
component: <name or symbol>
implementation_status: <CURRENT | TEST_ONLY | HISTORICAL_OR_LEGACY | UNKNOWN>
wiring_status: <WIRED | UNWIRED | UNKNOWN>
runtime_surfaces:
  - <MAIN_CLI | MCP_GATEWAY | LOCAL_RUNTIME | BENCHMARK | STANDALONE_OPS | TEST>
authority_roles:
  - <ROUTE_AUTHORITY | EXECUTION_AUTHORITY | GOVERNANCE_AUTHORITY | DERIVED_ONLY | NONE>
evidence_basis:
  - <evidence kind and exact path/symbol>
claim_ceiling: <short statement bounded by the strongest evidence>
```

The representation may be Markdown rather than YAML, but all six axes must remain explicit.

## Classification rules

### implementation_status

Use `CURRENT` only when current repository source physically supports the implementation claim.

Use `TEST_ONLY` when the meaningful evidence is limited to tests, fixtures, mocks, or test-only callers.

Use `HISTORICAL_OR_LEGACY` when evidence is historical, compatibility-only, superseded, or otherwise not evidence of current implementation use.

Use `UNKNOWN` when current implementation state cannot be established from available evidence.

Code existence alone does not prove current wiring.

### wiring_status

Use `WIRED` only when current physical evidence establishes a caller, entrypoint, service registration, dispatch path, or equivalent connection to a named runtime surface.

Use `UNWIRED` only when available evidence is sufficient to support absence within the explicitly examined scope.

If search or evidence coverage is incomplete, use `UNKNOWN` rather than converting “not found” into “unwired”.

Wiring on one runtime surface does not imply wiring on every runtime surface.

### runtime_surfaces

List only physically evidenced surfaces.

A component may be wired to `MCP_GATEWAY` while not being wired to `MAIN_CLI`.

Do not collapse surface-specific evidence into a global `WIRED_CURRENT` or `PRESENT_UNWIRED` label.

Use `TEST` only for test execution evidence.

### authority_roles

Do not infer authority from class names, filenames, package metadata, call frequency, tests, or architectural-looking names.

CapabilityPlanner and HybridRouteDecision remain route authority.

A component may be operationally wired while having `authority_roles: [NONE]`.

OpenWiki itself has no route, approval, integration, release, or governance authority.

### evidence_basis

Prefer current physical evidence such as:

* current source path and symbol;
* current caller or entrypoint;
* current service/adapter registration;
* current dispatch path;
* current runtime or receipt evidence when physically available.

Keep weaker evidence explicitly weaker:

* tests prove tested behavior only;
* fixtures and mocks do not prove production wiring;
* package metadata proves presence, not invocation;
* class or symbol existence proves existence, not current use;
* historical documents do not prove current wiring;
* generated documentation does not prove its own claims.

Name the exact evidence path or symbol whenever practical.

### claim_ceiling

The claim ceiling must never exceed the strongest evidence basis.

State the narrowest supportable claim.

If evidence is source-only, do not claim live-runtime behavior.

If evidence is test-only, do not claim production wiring.

If evidence is ambiguous or conflicting, preserve the ambiguity.

## False-currentness defenses

Do not infer that a component is currently active merely because:

* its class exists;
* a package exports it;
* a test imports it;
* a historical document names it;
* a roadmap or Task Card plans it;
* a generated page previously described it.

Do not infer that a component is absent merely because one bounded search did not find a caller.

Do not turn planned work into current implementation evidence.

## Runtime-wiring evidence discipline

A current class, module, function, or package definition proves implementation presence only. It does not by itself prove runtime wiring.

Before assigning `wiring_status: WIRED`, require at least one current non-test physical wiring witness for every claimed runtime surface, such as:

* a current caller;
* a current entrypoint;
* a current service or adapter registration;
* a current dispatch path;
* a current runtime receipt physically bound to that surface.

Do not infer `MAIN_CLI`, `MCP_GATEWAY`, `LOCAL_RUNTIME`, `BENCHMARK`, or any other runtime surface merely from:

* the component's directory or module name;
* documentation or historical reports;
* package exports;
* tests, mocks, fixtures, or test helpers;
* a benchmark-related name without a current benchmark caller;
* architectural intent or roadmap text.

If current evidence consists of the implementation definition plus test callers only:

```yaml
implementation_status: TEST_ONLY
wiring_status: UNKNOWN
runtime_surfaces:
  - TEST
authority_roles:
  - NONE
```

Use `UNWIRED` instead of `UNKNOWN` only when an explicitly bounded current-source search provides sufficient negative evidence for the examined scope.

Never upgrade a test-only caller into `LOCAL_RUNTIME` or `BENCHMARK` wiring.

For every claimed non-TEST runtime surface, name the exact current caller, entrypoint, registration, dispatch path, or runtime receipt in `evidence_basis`.

## Workflow trigger truth

When describing a GitHub Actions workflow's trigger mode, inspect the current workflow's exact `on:` keys.

`workflow_dispatch` means manual-only.

Describe a workflow as scheduled only when the current workflow physically contains a `schedule:` trigger.

Do not convert an intended future schedule, generic OpenWiki template wording, or historical workflow behavior into current operational truth.

## Surface-specific example rule

If current evidence shows a component instantiated by the MCP Gateway but not by the main CLI, represent that as surface-specific wiring, for example:

```yaml
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MCP_GATEWAY
authority_roles:
  - NONE
```

Do not describe the same evidence as globally unwired simply because `MAIN_CLI` does not instantiate it.

If a component has only test evidence, preserve that distinction, for example:

```yaml
implementation_status: TEST_ONLY
runtime_surfaces:
  - TEST
authority_roles:
  - NONE
```

Set `wiring_status` to `UNWIRED` only if the examined scope genuinely supports that negative claim; otherwise use `UNKNOWN`.

## Conflicts and uncertainty

When evidence conflicts:

1. state the conflicting evidence;
2. prefer current physical source/runtime evidence over historical prose;
3. preserve the lower-authority source as historical or uncertain;
4. do not synthesize a stronger claim than either source supports.

When evidence is insufficient, say `UNKNOWN`.

## Write boundary

OpenWiki documentation output belongs under `openwiki/`.

Do not intentionally write to `nexus_wiki_vault/`.

Do not intentionally modify repository governance, routing, approval, integration, release, or model-workforce contracts.

Any repository-side effect outside the permitted OpenWiki output is a containment failure, not an authorized documentation update.

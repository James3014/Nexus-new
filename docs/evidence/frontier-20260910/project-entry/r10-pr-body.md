Project Entry now restores the persisted authority binding for an exact repository and Issue and passes its validated selectors to canonical execution readiness. This closes the gap where an existing task was rehydrated but its grant context was omitted. Conflicting identities, tampered envelopes, missing hashes and incomplete material bindings fail closed; genuine no-task observation remains supported.

Validation on source `6d1e32216434bdda7930c0cf21921209d9243c6d`: 639 tests passed across the two affected suites; 17 independent fresh-process persisted composition cases passed, including canonical grant denial controls and no-write readback. Ruff retains seven exact-base findings with no new findings; diff check passed. A separate receipt-only commit binds this accepted source and the current Gateway predecessor for reversible deployment.

Refs #842. Native ChatGPT reacceptance and Issue closure follow deployment; this PR alone does not assert runtime completion.

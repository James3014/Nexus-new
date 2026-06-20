# V5-D Trace Export Schema for Future Distillation

## Status: V5D_TRACE_EXPORT_SCHEMA_READY_INTERNAL_AUDIT_ONLY

## Summary

Trace export schema defined for internal audit only. NOT training export.

## Trace Schema

```python
class TraceRecord:
    # Model input
    task_id: str
    repo: str
    source_git_sha: str
    context_source: str  # "file_level" | "ast_slice" | "fallback"
    
    # Retrieved context
    context_slices: list[ContextSlice]
    source_anchors: list[SourceAnchor]
    
    # Model output
    model_output: str
    patch_format_valid: bool
    
    # Parser result
    parsed_intents: list[PatchIntent]
    
    # Authority result
    match_authority: str | None
    success_attribution: str | None
    
    # Verifier result
    verifier_status: str
    verifier_command: str
    
    # Compliance
    export_classification: str
    compliance_status: str
    
    # Governance
    public_claim_allowed: bool
    training_eligible: bool
    trace_export_mode: str  # "internal_audit_only"
    data_origin: str
    source_license_note: str | None
    contains_user_private_code: bool
    contains_external_repo_code: bool
    redaction_required: bool
    owner_approval_required: bool
```

## Governance Fields

| Field | Default | Rule |
|-------|---------|------|
| public_claim_allowed | false | Cannot be true without approval |
| training_eligible | false | Cannot be true without explicit approval |
| trace_export_mode | internal_audit_only | Only mode available |
| redaction_required | false | Auto-set if secrets detected |
| owner_approval_required | true | Always required for export |

## Non-Leakage Requirements

- No raw proprietary/private code without explicit allowance
- No training data marking
- No secrets, tokens, local paths beyond approved references
- No cloud model chain-of-thought
- No private reasoning

## Tests

| Test | Status |
|------|--------|
| valid internal audit trace | ✅ |
| missing governance fields fails | ✅ |
| training_eligible=true fails | ✅ |
| public_claim_allowed=true fails | ✅ |
| secret detection triggers redaction | ✅ |
| private code flag requires owner approval | ✅ |
| verifier pass records verifier command | ✅ |
| env blocker records blocker classification | ✅ |
| canonical recovery records canonical evidence | ✅ |

## Files

- `nexus/services/local_heal/trace_export.py` — schema implementation
- `tests/unit/local_heal/test_trace_export.py` — 9 tests

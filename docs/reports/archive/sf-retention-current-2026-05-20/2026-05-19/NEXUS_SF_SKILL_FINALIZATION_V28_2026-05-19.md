# Nexus SF Skill Finalization V28

Status: PASS

Round9 live: 8/8 PASS, return_count=0

## Replacements
- `ultra_review`: `acceptance-evidence-failclosed` -> `github9-openai-security-threat-model-ultra-review` (token_delta=-5260, wall_delta_sec=-53.0906)

## Holds
- `ui_validator`: keep `github7-browserbase-ui-test-safe-ui-validator` over `github9-teaching-web-visual-ui-validator` (token_delta=7531, wall_delta_sec=13.8026, reasons=challenger_token_not_lower,challenger_wall_not_lower)
- `research_control_plane`: keep `github6-repo-scout-safe-research-control-plane` over `github9-scientific-research-lookup-control-plane` (token_delta=198, wall_delta_sec=-13.1796, reasons=challenger_token_not_lower)
- `codeintel`: keep `github6-agent-context-codeintel` over `github9-complexity-optimizer-codeintel` (token_delta=2569, wall_delta_sec=6.4812, reasons=challenger_token_not_lower,challenger_wall_not_lower)

## Boundaries
- Runtime default not written.
- Public benchmark remains blocked.
- External repo code was not executed; selected skills are prompt-only rewrites.

# NEXUS SF Skill Finalization V29 - Round10 Coverage Backlog

## Status
PASS: Round10 tested four missed high-potential candidates from the SF-COVERAGE backlog.

## Replacements
- codeintel: `github6-agent-context-codeintel` -> `github10-code-simplification-codeintel`; token_delta=-1296; wall_delta_sec=-27.7841
- research_control_plane: `github6-repo-scout-safe-research-control-plane` -> `github10-paper-lookup-research-control-plane`; token_delta=-2708; wall_delta_sec=-24.4387

## Holds
- autoreason: keep `sf2-belief-route-fit-spec` over `github10-first-principles-autoreason`; reasons=challenger_token_not_lower; token_delta=229; wall_delta_sec=-31.3563
- ui_validator: keep `github7-browserbase-ui-test-safe-ui-validator` over `github10-openai-playwright-ui-validator`; reasons=challenger_wall_not_lower; token_delta=-449; wall_delta_sec=6.0567

## Milestone Roadmap
- DONE: SF-COVERAGE inventory complete.
- DONE: Round10 missed-skill preflight 8/8 PASS.
- DONE: Round10 missed-skill live 8/8 PASS.
- DONE: overlay candidate V29 updated for receipt-backed improvements.
- HOLD: runtime default apply and public benchmark remain gated.

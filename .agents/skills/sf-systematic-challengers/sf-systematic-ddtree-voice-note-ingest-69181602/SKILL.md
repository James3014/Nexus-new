---
name: sf-systematic-ddtree-voice-note-ingest-69181602
description: Ingest a voice note with exact-phrasing preservation (never paraphrased). Routes content to originals/, concepts/, people/, companies/, ideas/, personal/, or voice-notes/ based on a decision tree. The user's exact words are the signal.
metadata: {"source_status":"systematic_compiled_interface", "runtime_eligible":false, "ablation_eligible":true}
---

# voice-note-ingest

## Load when
- "voice note"
- "ingest this voice memo"
- "transcribe and file"
- "voice note ingest"
- "save this audio note"

## Do not load when
- runtime default promotion is requested without receipt review

## Required receipts
- selected
- injected
- used
- evidence_present
- gate_passed
- outcome_contributed

## Source
- /private/tmp/nexus-sf-round8/garrytan-gbrain/skills/voice-note-ingest/SKILL.md

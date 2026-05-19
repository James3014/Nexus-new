---
name: sf-systematic-belief-diffdock-e75e5687
description: Diffusion-based molecular docking. Predict protein-ligand binding poses from PDB/SMILES, confidence scores, virtual screening, for structure-based drug design. Not for affinity prediction.
metadata: {"source_status":"systematic_compiled_interface", "runtime_eligible":false, "ablation_eligible":true}
---

# diffdock

## Load when
- "Dock this ligand to a protein" or "predict binding pose"
- "Run molecular docking" or "perform protein-ligand docking"
- "Virtual screening" or "screen compound library"
- "Where does this molecule bind?" or "predict binding site"
- Structure-based drug design or lead optimization tasks

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
- /private/tmp/nexus-sf-round9/K-Dense-AI-scientific-agent-skills/scientific-skills/diffdock/SKILL.md

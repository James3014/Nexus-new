#!/usr/bin/env python3
import json
import os
import sys

# Ensure templates are discoverable
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

def load_fragilities():
    # In a real scenario, this would come from nx_impact.py results
    # For the prototype, we mock a list of detected fragilities.
    return [
        {
            "id": "FRAG_001",
            "type": "SCHEMA_UI_DIRECT_BINDING",
            "target": "script.js",
            "entity": "questions",
            "fields": "id,content,options,answer"
        }
    ]

def generate_patch_for_fragility(f):
    target = f["target"]
    entity = f["entity"]
    fields = f["fields"]
    
    # 1. Generate the fix content using the template
    # Here we simulate calling the adapter_template.py logic
    from patch_templates.adapter_template import generate_adapter
    fix_body = generate_adapter(entity, fields)
    
    # 2. Create the unified diff patch
    # For prototype, we generate a patch that prepends the fix
    patch_content = f"""--- {target}
+++ {target}
@@ -1,3 +1,15 @@
+{fix_body}
+
"""
    return patch_content

def main():
    print("🕸️ Nexus Hybrid Patcher: Generating Architectural Remedies...")
    fragilities = load_fragilities()
    
    for f in fragilities:
        print(f"🛠️  Processing {f['id']} ({f['type']}) for {f['target']}...")
        patch = generate_patch_for_fragility(f)
        
        patch_file = f"nexus_fix_{f['id']}.patch"
        with open(patch_file, "w") as pf:
            pf.write(patch)
            
        print(f"✅ Generated Patch: {patch_file}")
    
    print("\n🏁 Patch Generation Complete.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse
import os

def generate_repair_patch(target_file, entity_name, fields):
    # This is a specialized generator for SCHEMA_UI_DIRECT_BINDING
    # It generates a unified diff to insert the Adapter and update usage.
    
    adapter_class = f"""
export class {entity_name.capitalize()}Adapter {{
    static transform(raw) {{
        return {{
            id: raw.id,
{chr(10).join([f"            {f}: raw.{f}," for f in fields])}
        }};
    }}
}}
"""
    # A real implementation would parse the AST to find where to insert.
    # For the prototype, we generate a patch that prepends the adapter.
    
    patch_content = f"""--- {target_file}
+++ {target_file}
@@ -1,3 +1,15 @@
+{adapter_class}
+
"""
    return patch_content

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--entity", required=True)
    parser.add_argument("--out", default="nexus_repair.patch")
    args = parser.parse_args()

    # Mock fields for demo
    fields = ["content", "options", "answer"]
    patch = generate_repair_patch(args.target, args.entity, fields)
    
    with open(args.out, "w") as f:
        f.write(patch)
    
    print(f"✅ Generated Nexus Repair Patch: {args.out}")
    print(f"👉 To apply: git apply {args.out}")

if __name__ == "__main__":
    main()

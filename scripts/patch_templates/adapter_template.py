#!/usr/bin/env python3
import argparse

def generate_adapter(entity_name, fields):
    fields_list = fields.split(",")
    mapping = "\n".join([f"            {f}: raw.{f}," for f in fields_list])
    
    template = f"""
export class {entity_name.capitalize()}Adapter {{
    static transform(raw) {{
        return {{
            id: raw.id,
{mapping}
        }};
    }}
}}
"""
    return template

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity", required=True)
    parser.add_argument("--fields", required=True)
    args = parser.parse_args()
    print(generate_adapter(args.entity, args.fields))

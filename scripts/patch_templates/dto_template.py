#!/usr/bin/env python3
import argparse

def generate_dto(entity_name, fields):
    fields_list = fields.split(",")
    init_args = ", ".join([f"{f}=None" for f in fields_list])
    assignments = "\n".join([f"        self.{f} = {f}" for f in fields_list])
    
    template = f"""
class {entity_name.capitalize()}DTO:
    def __init__(self, {init_args}):
{assignments}

    @classmethod
    def from_row(cls, row):
        return cls(
{chr(10).join([f"            {f}=row.get('{f}')," for f in fields_list])}
        )
"""
    return template

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity", required=True)
    parser.add_argument("--fields", required=True)
    args = parser.parse_args()
    print(generate_dto(args.entity, args.fields))

#!/usr/bin/env python3
import argparse

def generate_deprecation_log(field_name, alternate=None):
    alt_msg = f", please use '{alternate}' instead" if alternate else ""
    template = f"""
def get_{field_name}_deprecated(obj):
    print(f"⚠️ [DEPRECATED] Field '{field_name}' accessed by {{obj}}{alt_msg}")
    # Telemetry.log_event("deprecation_hit", {{"field": "{field_name}"}})
    return obj.{field_name}
"""
    return template

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", required=True)
    parser.add_argument("--alternate", default=None)
    args = parser.parse_args()
    print(generate_deprecation_log(args.field, args.alternate))

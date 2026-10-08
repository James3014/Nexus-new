def build_record(name, fields={}):  # BUG: mutable default dict shared across calls
    fields.setdefault("name", name)
    return fields

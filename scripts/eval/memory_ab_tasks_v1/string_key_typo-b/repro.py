from headers import content_type

got = content_type({"Content-Type": "application/json"})
assert got == "application/json", f"content_type got {got!r} want application/json"

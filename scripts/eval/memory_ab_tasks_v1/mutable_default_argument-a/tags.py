def collect_tags(tag, tags=[]):  # BUG: mutable default argument shared across calls
    tags.append(tag)
    return tags

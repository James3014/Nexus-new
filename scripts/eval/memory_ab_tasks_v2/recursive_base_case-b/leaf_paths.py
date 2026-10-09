def leaf_paths(node, path=()):
    """Return (path, value) pairs for every scalar leaf of nested dicts and lists.

    Dict keys and list indexes form the path. None is a scalar leaf. Empty dicts
    and lists contribute nothing.
    """
    if isinstance(node, dict):
        if not node:
            return [(path, node)]  # BUG: an empty dict is reported as a leaf
        out = []
        for key, child in node.items():
            out.extend(leaf_paths(child, path + (key,)))
        return out
    if isinstance(node, list):
        out = []
        for index, child in enumerate(node):
            out.extend(leaf_paths(child, path + (index,)))
        return out
    return [(path, node)]

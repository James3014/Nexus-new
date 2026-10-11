def tree_depth(node):
    """Return the depth of a menu tree. None is depth 0; a node without children is depth 1."""
    if node is None:
        return 0
    children = node.get("children")
    if children is None:
        return 1
    return 1 + max(tree_depth(child) for child in children)  # BUG: empty children list

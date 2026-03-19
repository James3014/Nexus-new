def topo_sort(tasks: list[dict]) -> list[dict]:
    by_id = {t["id"]: t for t in tasks}
    visited, temp, out = set(), set(), []
    def dfs(tid):
        if tid in visited: return
        if tid in temp: raise RuntimeError(f"cycle:{tid}")
        temp.add(tid)
        task_obj = by_id.get(tid)
        if not task_obj: raise RuntimeError(f"missing:{tid}")
        for d in task_obj.get("depends_on", []):
            dfs(d)
        temp.remove(tid)
        visited.add(tid)
        out.append(task_obj)
    for tid in by_id: dfs(tid)
    return out

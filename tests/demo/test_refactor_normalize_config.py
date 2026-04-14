from nexus.demo.refactor_normalize_config import normalize_hosts

def test_normalize_hosts_dedup_and_sort():
    got = normalize_hosts([" API.local ", "db.local", "api.local", ""])
    assert got == ["api.local", "db.local"]

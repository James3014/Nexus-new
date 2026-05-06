from nexus.services.mem_palace import MemPalace


class FakeBeliefStore:
    def __init__(self, rows):
        self.rows = rows
        self.statuses = []

    def list_beliefs(self, status="ACTIVE"):
        self.statuses.append(status)
        return list(self.rows)


class FakeConfigStore:
    def get_router_bias(self):
        return [0.1, 0.2, 0.7]


class FakeStorage:
    def __init__(self):
        self.scoped_tenants = []
        self.retrieve_calls = []

    def scoped_access(self, tenant_id):
        self.scoped_tenants.append(tenant_id)
        return self

    def retrieve(self, query, **kwargs):
        self.retrieve_calls.append({"query": query, **kwargs})
        return [{"tenant_id": self.scoped_tenants[-1], "content": query}]

    def store(self, tenant_id, artifact_type, data):
        return {"tenant_id": tenant_id, "artifact_type": artifact_type, "data": data}


def test_audit_logic():
    palace = MemPalace()
    assert palace.audit_action("D", "Check evidence in LDB") is True
    assert palace.audit_action("D", "Just guessing") is False


def test_mem_palace_uses_injected_belief_and_config_stores():
    beliefs = [
        {"id": "b1", "content": "require evidence before patch", "status": "ACTIVE", "trust_level": "TRUSTED"},
        {"id": "b2", "content": "forbid unsafe shell", "status": "ACTIVE", "trust_level": "UNTRUSTED"},
        {"id": "b3", "content": "prefer small patch", "status": "ACTIVE", "trust_level": "TRUSTED"},
    ]
    belief_store = FakeBeliefStore(beliefs)
    palace = MemPalace(belief_store=belief_store, config_store=FakeConfigStore())

    constraints = palace.get_skill_constraints()

    assert belief_store.statuses == ["ACTIVE"]
    assert constraints["require"] == ["require evidence before patch"]
    assert constraints["forbid"] == []
    assert constraints["prefer"] == ["prefer small patch"]
    assert palace.get_router_bias() == [0.1, 0.2, 0.7]


def test_mem_palace_retrieve_from_shards_uses_tenant_scoped_storage():
    storage = FakeStorage()
    palace = MemPalace(storage=storage)

    rows = palace.retrieve_from_shards("tenant-a", "scoped evidence", artifact_type="lesson", limit=2)

    assert storage.scoped_tenants == ["tenant-a"]
    assert storage.retrieve_calls == [{"query": "scoped evidence", "artifact_type": "lesson", "limit": 2}]
    assert rows == [{"tenant_id": "tenant-a", "content": "scoped evidence"}]


def test_mem_palace_retrieve_from_shards_fails_closed_without_tenant():
    storage = FakeStorage()
    palace = MemPalace(storage=storage)

    assert palace.retrieve_from_shards("", "scoped evidence") == []
    assert storage.scoped_tenants == []

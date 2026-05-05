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

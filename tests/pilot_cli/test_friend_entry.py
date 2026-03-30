import os

from scripts import nexus_pilot_friend


def test_friend_entry_sets_defaults_and_forwards_tenant(monkeypatch):
    captured = {}

    monkeypatch.delenv("NEXUS_PILOT_GATEWAY_URL", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_PROVIDER", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_MODEL", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_TENANT_ID", raising=False)
    monkeypatch.setattr("scripts.nexus_pilot_friend.pilot_main", lambda: captured.setdefault("called", True) or 0)
    monkeypatch.setattr("sys.argv", ["nexus-pilot-friend", "pilot_b"])

    nexus_pilot_friend.main()

    assert captured["called"] is True
    assert os.environ["NEXUS_PILOT_TENANT_ID"] == "pilot_b"
    assert os.environ["NEXUS_PILOT_GATEWAY_URL"] == nexus_pilot_friend.DEFAULT_GATEWAY
    assert os.environ["NEXUS_PILOT_PROVIDER"] == nexus_pilot_friend.DEFAULT_PROVIDER
    assert os.environ["NEXUS_PILOT_MODEL"] == nexus_pilot_friend.DEFAULT_MODEL

import json

from nexus.infrastructure.storage_implementations import LocalCacheStore
from nexus.services.mem_palace import MemPalace


class _NoopStore:
    pass


def _palace(root):
    return MemPalace(
        str(root),
        storage=_NoopStore(),
        cache=LocalCacheStore(),
        belief_store=_NoopStore(),
        config_store=_NoopStore(),
    )


def _write_blacklist(root, patterns):
    path = root / "nexus" / "config" / "ethical_blacklist.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"patterns": patterns}), encoding="utf-8")


def test_verify_context_loads_blacklist_without_prior_sync(tmp_path):
    """A fresh process must enforce the on-disk blacklist without an explicit sync()."""
    _write_blacklist(tmp_path, ["rm -rf /"])

    verdict = _palace(tmp_path).verify_context("please run rm -rf / now")

    assert verdict == {"status": "BLOCKED", "reason": "rm -rf /"}


def test_verify_loads_blacklist_without_prior_sync(tmp_path):
    _write_blacklist(tmp_path, ["forbidden-token"])

    kept = _palace(tmp_path).verify([{"c": "ok"}, {"c": "has forbidden-token"}])

    assert kept == [{"c": "ok"}]


def test_sync_reports_missing_blacklist_source(tmp_path):
    result = _palace(tmp_path).sync()

    assert result["synced_patterns"] == 0
    assert result["blacklist_source"] == "missing"


def test_injected_cache_patterns_are_not_overwritten(tmp_path):
    _write_blacklist(tmp_path, ["from-file"])
    palace = _palace(tmp_path)
    palace.cache.sadd("nexus:ethical_blacklist", "injected")

    assert palace.verify_context("contains injected")["status"] == "BLOCKED"

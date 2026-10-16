# M3: SkillSignalSet Added to core/capability_signal_set.py

**Status**: M3_PASS

## Files changed
- `nexus/core/capability_signal_set.py` — 加 `SkillSignalSet` frozen dataclass (與 engine/ 同構)
- `tests/core/test_capability_signal_set.py` — 新建: 4 個 M3 test

## Test counts
- 4 new (M3) PASS
- Engine import 仍可正常 import (向後相容)

## Changes
1. `asdict` import added to `core/capability_signal_set.py`
2. `SkillSignalSet` dataclass 與 engine/ 版本欄位一致: `top_skill_ids`, `skill_confidence`, `trust_level`, `source`, `to_dict()`

## Governance boundary
- 不修改 `nexus/engine/capability_contracts.py` (向後相容)
- 兩個 SkillSignalSet 定義可並存, `to_dict()` 輸出一致

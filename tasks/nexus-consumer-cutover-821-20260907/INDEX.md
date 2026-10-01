# G9 bounded Core namespace/script retirement

- Goal: NEXUS-THREE-REPO-CONSUMER-CUTOVER-20260907
- Issue: James3014/Nexus-new#821
- Active card: [00-retire-core-package-collision.md](00-retire-core-package-collision.md)
- G8 dependency: FULL_CONSUMER_CUTOVER_VERIFIED, main `4887d8f6a3faf50d6b600f2c170526e08d4bf408`
- G8 receipt SHA-256: `855137d51b9123c4a342051e3254616957bbaadc50673d0e25e47f29c3d413d0`
- Coordinator: primary-codex-coordinator
- Claim mode: MANUAL_DISPATCH
- AUTO_CHAIN: false
- Allowed production delta: three legacy Core packaging declarations only
- Source/history deletion: none
- Worker scope: pyproject.toml plus new focused packaging test
- Independent acceptance and protected GitHub merge remain primary responsibilities
- Current status: READY_FOR_BOUNDED_IMPLEMENTATION; no G9 completion claim

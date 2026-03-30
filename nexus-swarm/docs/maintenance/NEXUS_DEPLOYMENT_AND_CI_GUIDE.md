# NEXUS_DEPLOYMENT_AND_CI_GUIDE

## CI 整合 (GitHub Actions)
```yaml
env:
  NEXUS_GATE_BYPASS: "true"
  NEXUS_SWARM_TOKEN: ${{ secrets.NEXUS_TOKEN }}
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/engine/nexus_cli.py audit --path .
```

## 部署需求
- **Manager**: 需暴露 9000 (API) 與 9100 (Metrics) 端口。
- **Nodes**: 需具備 Python 3.x 環境並能存取目標 Workspace。

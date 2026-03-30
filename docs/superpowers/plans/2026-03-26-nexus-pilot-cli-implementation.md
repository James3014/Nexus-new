# Nexus Pilot CLI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個新的 chat-first、task-capable、closed-core `Nexus Pilot CLI`，讓 pilot tenant 以自己的 API key 接入 Nexus，先感受到高速對話，再升級為治理任務。

**Architecture:** 新 CLI 採 Hybrid 架構。本地 CLI Shell 與 Adapter 負責 onboarding、session、快速互動與 mode routing；遠端 Nexus runtime / gateway 保留 closed-core 治理能力。第一版先重用既有 `scripts/engine/nexus_cli.py` 可復用能力，但不再把 `scripts/nexus_chat_cli.py` 當產品主體。

**Tech Stack:** Python 3.9+、argparse 或輕量 CLI layer、受控 session storage、既有 Nexus engine/service、遠端 gateway integration、pytest

---

## 檔案結構與責任切分

- 修改：`scripts/nexus_chat_cli.py`
  角色：從原型聊天殼轉為新的 pilot CLI 入口，或作為過渡入口包裝新模組。
- 新增：`nexus/pilot_cli/session.py`
  角色：管理 tenant、provider、model、workspace、session secret state。
- 新增：`nexus/pilot_cli/onboarding.py`
  角色：首次啟動引導、設定收集、預設值處理。
- 新增：`nexus/pilot_cli/router.py`
  角色：Fast Lane / Battle Lane 意圖判斷與 escalation routing。
- 新增：`nexus/pilot_cli/ui.py`
  角色：主畫面、首屏狀態列、戰報輸出格式。
- 新增：`nexus/pilot_cli/commands.py`
  角色：處理 `/mount`、`/govern`、`/status`、`/provider`、`/model`、`/reset`、`/exit`。
- 新增：`nexus/pilot_cli/gateway.py`
  角色：對接遠端 Nexus runtime / gateway 的薄封裝。
- 新增：`tests/pilot_cli/test_onboarding.py`
  角色：測 onboarding 流程與 session 組裝。
- 新增：`tests/pilot_cli/test_router.py`
  角色：測 Fast Lane / Battle Lane 路由與升級判斷。
- 新增：`tests/pilot_cli/test_commands.py`
  角色：測 slash command 行為。
- 新增：`tests/pilot_cli/test_secret_handling.py`
  角色：測 API key 遮罩、session 清理、禁止外漏。

## Chunk 1: 入口重構與 Session 骨架

### Task 1: 建立 pilot CLI 模組骨架

**Files:**
- Create: `nexus/pilot_cli/session.py`
- Create: `nexus/pilot_cli/ui.py`
- Modify: `scripts/nexus_chat_cli.py`
- Test: `tests/pilot_cli/test_onboarding.py`

- [ ] **Step 1: 寫失敗測試，確認 CLI 能建立空 session**

```python
def test_session_defaults():
    from nexus.pilot_cli.session import PilotSession

    session = PilotSession()
    assert session.tenant_id is None
    assert session.mode == "FAST"
```

- [ ] **Step 2: 執行測試，確認目前失敗**

Run: `pytest tests/pilot_cli/test_onboarding.py::test_session_defaults -v`
Expected: FAIL，因模組或類別尚不存在

- [ ] **Step 3: 寫最小實作**

建立 `PilotSession`，至少包含：
- `tenant_id`
- `provider`
- `model`
- `workspace`
- `mode`
- `api_key`

- [ ] **Step 4: 讓 `scripts/nexus_chat_cli.py` 轉為新入口 shim**

最小目標：
- 保留既有啟動命令不變
- 內部改呼叫新的 pilot CLI 主循環

- [ ] **Step 5: 重新執行測試，確認通過**

Run: `pytest tests/pilot_cli/test_onboarding.py::test_session_defaults -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/nexus_chat_cli.py nexus/pilot_cli/session.py nexus/pilot_cli/ui.py tests/pilot_cli/test_onboarding.py
git commit -m "feat: scaffold nexus pilot cli session core"
```

### Task 2: 建立首屏與狀態列輸出

**Files:**
- Modify: `nexus/pilot_cli/ui.py`
- Test: `tests/pilot_cli/test_onboarding.py`

- [ ] **Step 1: 寫失敗測試，確認首屏包含 tenant/provider/model/mode**

```python
def test_render_main_screen_includes_session_state():
    from nexus.pilot_cli.session import PilotSession
    from nexus.pilot_cli.ui import render_main_screen

    session = PilotSession(
        tenant_id="pilot_a",
        provider="OpenAI",
        model="gpt-5.4",
        workspace="~/project",
    )
    screen = render_main_screen(session)
    assert "Tenant: pilot_a" in screen
    assert "Mode: FAST" in screen
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `pytest tests/pilot_cli/test_onboarding.py::test_render_main_screen_includes_session_state -v`
Expected: FAIL

- [ ] **Step 3: 寫最小實作**

輸出：
- 標題
- tenant/provider/model/workspace/mode
- 提示文案
- commands 清單

- [ ] **Step 4: 重新執行測試，確認通過**

Run: `pytest tests/pilot_cli/test_onboarding.py::test_render_main_screen_includes_session_state -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nexus/pilot_cli/ui.py tests/pilot_cli/test_onboarding.py
git commit -m "feat: add nexus pilot cli main screen"
```

## Chunk 2: Onboarding 與 Command 面

### Task 3: 建立首次啟動 onboarding 流程

**Files:**
- Create: `nexus/pilot_cli/onboarding.py`
- Modify: `nexus/pilot_cli/session.py`
- Test: `tests/pilot_cli/test_onboarding.py`

- [ ] **Step 1: 寫失敗測試，確認 onboarding 能逐步組出 session**

```python
def test_onboarding_builds_session_from_answers():
    from nexus.pilot_cli.onboarding import build_session_from_answers

    session = build_session_from_answers(
        tenant_id="tenant_a",
        provider="OpenAI",
        api_key="sk-test",
        model="gpt-5.4",
        workspace="~/repo",
    )
    assert session.tenant_id == "tenant_a"
    assert session.provider == "OpenAI"
    assert session.model == "gpt-5.4"
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `pytest tests/pilot_cli/test_onboarding.py::test_onboarding_builds_session_from_answers -v`
Expected: FAIL

- [ ] **Step 3: 寫最小實作**

包含：
- 輸入驗證
- provider/model 預設值
- workspace 可略過
- session 建立

- [ ] **Step 4: 加入 key 遮罩輔助函式**

至少保證 UI 層不直接印出完整 key。

- [ ] **Step 5: 重跑測試，確認通過**

Run: `pytest tests/pilot_cli/test_onboarding.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add nexus/pilot_cli/onboarding.py nexus/pilot_cli/session.py tests/pilot_cli/test_onboarding.py
git commit -m "feat: add pilot cli onboarding flow"
```

### Task 4: 建立 slash commands 基礎框架

**Files:**
- Create: `nexus/pilot_cli/commands.py`
- Test: `tests/pilot_cli/test_commands.py`

- [ ] **Step 1: 寫失敗測試，確認 `/status` 能回傳 session 摘要**

```python
def test_status_command_returns_session_summary():
    from nexus.pilot_cli.session import PilotSession
    from nexus.pilot_cli.commands import handle_command

    session = PilotSession(tenant_id="pilot_a", provider="OpenAI", model="gpt-5.4")
    output = handle_command("/status", session)
    assert "pilot_a" in output
    assert "OpenAI" in output
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `pytest tests/pilot_cli/test_commands.py::test_status_command_returns_session_summary -v`
Expected: FAIL

- [ ] **Step 3: 寫最小實作**

先支援：
- `/status`
- `/reset`
- `/exit`

- [ ] **Step 4: 擴充 command registry**

預留：
- `/mount`
- `/govern`
- `/provider`
- `/model`

- [ ] **Step 5: 重跑測試，確認通過**

Run: `pytest tests/pilot_cli/test_commands.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add nexus/pilot_cli/commands.py tests/pilot_cli/test_commands.py
git commit -m "feat: add pilot cli command layer"
```

## Chunk 3: Fast Lane / Battle Lane 路由

### Task 5: 建立意圖路由器

**Files:**
- Create: `nexus/pilot_cli/router.py`
- Test: `tests/pilot_cli/test_router.py`

- [ ] **Step 1: 寫失敗測試，確認一般問答留在 Fast Lane**

```python
def test_router_keeps_general_question_in_fast_lane():
    from nexus.pilot_cli.router import route_input

    route = route_input("這個 stack trace 是什麼意思")
    assert route.lane == "FAST"
```

- [ ] **Step 2: 寫失敗測試，確認修復意圖升級 Battle Lane**

```python
def test_router_marks_fix_request_for_battle_lane():
    from nexus.pilot_cli.router import route_input

    route = route_input("幫我修這個 bug")
    assert route.lane == "BATTLE_CONFIRM"
```

- [ ] **Step 3: 執行測試，確認失敗**

Run: `pytest tests/pilot_cli/test_router.py -v`
Expected: FAIL

- [ ] **Step 4: 寫最小實作**

至少判斷：
- 一般問答
- stack trace / error 分析
- repo / govern / fix 類請求
- 需要確認的高風險升級

- [ ] **Step 5: 重跑測試，確認通過**

Run: `pytest tests/pilot_cli/test_router.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add nexus/pilot_cli/router.py tests/pilot_cli/test_router.py
git commit -m "feat: add fast and battle lane router"
```

### Task 6: 將主循環接上 router 與 command 層

**Files:**
- Modify: `scripts/nexus_chat_cli.py`
- Modify: `nexus/pilot_cli/commands.py`
- Modify: `nexus/pilot_cli/router.py`
- Test: `tests/pilot_cli/test_commands.py`
- Test: `tests/pilot_cli/test_router.py`

- [ ] **Step 1: 寫失敗測試，確認自然語言會走 router 而非 command parser**

- [ ] **Step 2: 執行測試，確認失敗**

Run: `pytest tests/pilot_cli/test_commands.py tests/pilot_cli/test_router.py -v`
Expected: FAIL

- [ ] **Step 3: 更新主循環**

邏輯：
- slash command -> command handler
- natural language -> router
- Fast Lane -> 快速回應 stub
- Battle Lane -> 回傳升級提示或治理 stub

- [ ] **Step 4: 重跑測試，確認通過**

Run: `pytest tests/pilot_cli/test_commands.py tests/pilot_cli/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/nexus_chat_cli.py nexus/pilot_cli/commands.py nexus/pilot_cli/router.py tests/pilot_cli/test_commands.py tests/pilot_cli/test_router.py
git commit -m "feat: wire pilot cli main loop"
```

## Chunk 4: Secret Handling 與 Gateway 接面

### Task 7: 建立 secret masking 與 session cleanup

**Files:**
- Modify: `nexus/pilot_cli/session.py`
- Create: `tests/pilot_cli/test_secret_handling.py`

- [ ] **Step 1: 寫失敗測試，確認 key 在狀態輸出中被遮罩**

```python
def test_api_key_is_masked_in_status_output():
    from nexus.pilot_cli.session import PilotSession

    session = PilotSession(api_key="sk-secret-123456")
    status = session.describe()
    assert "123456" not in status
```

- [ ] **Step 2: 寫失敗測試，確認 cleanup 後 key 被清空**

```python
def test_session_cleanup_removes_api_key():
    from nexus.pilot_cli.session import PilotSession

    session = PilotSession(api_key="sk-secret")
    session.clear_secrets()
    assert session.api_key is None
```

- [ ] **Step 3: 執行測試，確認失敗**

Run: `pytest tests/pilot_cli/test_secret_handling.py -v`
Expected: FAIL

- [ ] **Step 4: 寫最小實作**

包含：
- key masking
- `clear_secrets()`
- 避免 `repr()` 或 `describe()` 洩漏 key

- [ ] **Step 5: 重跑測試，確認通過**

Run: `pytest tests/pilot_cli/test_secret_handling.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add nexus/pilot_cli/session.py tests/pilot_cli/test_secret_handling.py
git commit -m "feat: add pilot cli secret handling"
```

### Task 8: 建立遠端 gateway 薄封裝

**Files:**
- Create: `nexus/pilot_cli/gateway.py`
- Test: `tests/pilot_cli/test_router.py`

- [ ] **Step 1: 寫失敗測試，確認 Battle Lane 可形成治理請求 payload**

- [ ] **Step 2: 執行測試，確認失敗**

Run: `pytest tests/pilot_cli/test_router.py -v`
Expected: FAIL

- [ ] **Step 3: 寫最小實作**

先不接完整遠端邏輯，只建立：
- tenant id
- provider
- model
- workspace
- user request
- lane

的 payload 與 stub client

- [ ] **Step 4: 重跑測試，確認通過**

Run: `pytest tests/pilot_cli/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nexus/pilot_cli/gateway.py tests/pilot_cli/test_router.py
git commit -m "feat: add pilot cli gateway stub"
```

## Chunk 5: 文件與驗證

### Task 9: 文件更新與使用說明

**Files:**
- Modify: `docs/superpowers/specs/2026-03-26-nexus-pilot-cli-design.md`
- Create or Modify: `docs/` 下對外使用說明文件

- [ ] **Step 1: 補上中文版使用方式與 v1 邊界**
- [ ] **Step 2: 記錄保留原啟動命令或新啟動命令**
- [ ] **Step 3: 寫清楚 API key handling 與 pilot 模式限制**
- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-03-26-nexus-pilot-cli-design.md docs
git commit -m "docs: document nexus pilot cli usage"
```

### Task 10: 整體驗證

**Files:**
- Test: `tests/pilot_cli/test_onboarding.py`
- Test: `tests/pilot_cli/test_commands.py`
- Test: `tests/pilot_cli/test_router.py`
- Test: `tests/pilot_cli/test_secret_handling.py`

- [ ] **Step 1: 執行 pilot CLI 測試集**

Run: `pytest tests/pilot_cli -v`
Expected: PASS

- [ ] **Step 2: 手動驗證 CLI 啟動流程**

Run: `/usr/bin/python3 /Users/jameschen/Workspace/nexus/scripts/nexus_chat_cli.py`
Expected:
- 可進 onboarding
- 可看到主畫面
- 可處理 `/status`
- 可對一般自然語言走 Fast Lane
- 可對修復請求顯示 Battle Lane 升級提示

- [ ] **Step 3: 記錄未完成項與下一階段風險**

至少列出：
- 遠端 runtime 尚為 stub 或最小整合
- 真正的高風險治理授權尚未全接
- provider 支援範圍尚有限

- [ ] **Step 4: Commit**

```bash
git add tests/pilot_cli
git commit -m "test: validate nexus pilot cli v1 flow"
```

Plan complete and saved to `docs/superpowers/plans/2026-03-26-nexus-pilot-cli-implementation.md`. Ready to execute?

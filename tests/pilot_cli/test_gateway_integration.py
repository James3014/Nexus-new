from nexus.pilot_cli.gateway import (
    _build_fastlane_prompt,
    _coerce_long_gemini_answer,
    _gemini_payload,
    _format_gemini_fastlane_response,
    chat_via_gateway,
    ensure_local_gateway_running,
    get_gateway_base_url,
    govern_via_gateway,
)
from nexus.pilot_cli.session import PilotSession


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {"content-type": "application/json"}

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


def test_get_gateway_base_url_prefers_env(monkeypatch):
    monkeypatch.setenv("NEXUS_PILOT_GATEWAY_URL", "http://localhost:9000")
    assert get_gateway_base_url() == "http://localhost:9000"


def test_chat_via_gateway_parses_json_message():
    session = PilotSession(tenant_id="pilot_a", provider="OpenAI", model="gpt-5.4")

    def fake_post(url, json_payload, headers=None, timeout=None):
        assert url.endswith("/chat")
        assert headers["X-Tenant-ID"] == "pilot_a"
        return DummyResponse(json_data={"message": "Gateway reply"})

    output = chat_via_gateway(session, "hello", post_fn=fake_post)
    assert output == "Gateway reply"


def test_govern_via_gateway_parses_task_response():
    session = PilotSession(tenant_id="pilot_a", provider="OpenAI", model="gpt-5.4")

    def fake_post(url, json_payload, headers=None, timeout=None):
        assert url.endswith("/govern")
        return DummyResponse(
            json_data={
                "task_id": "task-42",
                "status": "QUEUED",
                "summary": "Sensing: accepted",
            }
        )

    result = govern_via_gateway(session, "fix bug", post_fn=fake_post)
    assert result["task_id"] == "task-42"
    assert result["status"] == "QUEUED"
    assert session.active_task_id == "task-42"
    assert session.mode == "BATTLE"


def test_govern_via_gateway_falls_back_to_local_stub_on_failure():
    session = PilotSession(tenant_id="pilot_a", provider="OpenAI", model="gpt-5.4")

    def fake_post(url, json_payload, headers=None, timeout=None):
        raise RuntimeError("gateway offline")

    result = govern_via_gateway(session, "fix bug", post_fn=fake_post)
    assert result["status"] == "QUEUED"
    assert result["task_id"].startswith("pilot-task-")


def test_ensure_local_gateway_running_starts_proxy_when_status_fails(monkeypatch):
    calls = {"spawned": False, "checks": 0}

    monkeypatch.setenv("NEXUS_PILOT_GATEWAY_URL", "http://127.0.0.1:5005")

    def fake_get(url, timeout=None):
        calls["checks"] += 1
        if calls["spawned"] and calls["checks"] > 1:
            return DummyResponse(status_code=200, json_data={"status": "ok"})
        raise RuntimeError("offline")

    def fake_spawn():
        calls["spawned"] = True

    started = ensure_local_gateway_running(
        get_fn=fake_get,
        spawn_fn=fake_spawn,
        sleep_fn=lambda _: None,
        retries=2,
    )
    assert started is True
    assert calls["spawned"] is True


def test_ensure_local_gateway_running_skips_non_local_gateway(monkeypatch):
    monkeypatch.setenv("NEXUS_PILOT_GATEWAY_URL", "https://gateway.example.com")
    started = ensure_local_gateway_running(
        get_fn=lambda *args, **kwargs: None,
        spawn_fn=lambda: None,
        sleep_fn=lambda _: None,
    )
    assert started is False


def test_build_fastlane_prompt_for_long_question():
    prompt = _build_fastlane_prompt("x" * 1200)
    assert "長題快速壓縮分析模式" in prompt
    assert "結論、根因、為何會漏過、修補策略" in prompt
    assert "根因" in prompt
    assert "修補策略" in prompt


def test_gemini_payload_for_long_question_requests_json_schema():
    payload = _gemini_payload("x" * 1200)
    config = payload["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["maxOutputTokens"] >= 900
    schema = config["responseSchema"]
    assert schema["type"] == "OBJECT"
    assert "conclusion" in schema["properties"]
    assert "fix_strategy" in schema["properties"]


def test_chat_via_gateway_prefers_gemini_api_when_key_present(monkeypatch):
    session = PilotSession(
        tenant_id="pilot_a",
        provider="Gemini",
        model="gemini-2.5-flash",
        api_key="gemini-key",
    )

    captured = {}

    def fake_gemini_call(session_arg, user_request):
        captured["provider"] = session_arg.provider
        captured["request"] = user_request
        return "Gemini direct reply"

    output = chat_via_gateway(
        session,
        "這是一個很長很長的問題",
        gemini_fn=fake_gemini_call,
    )
    assert output == "Gemini direct reply"
    assert captured["provider"] == "Gemini"


def test_chat_via_gateway_falls_back_to_gateway_when_gemini_direct_fails():
    session = PilotSession(
        tenant_id="pilot_a",
        provider="Gemini",
        model="gemini-2.5-flash",
        api_key="gemini-key",
    )

    def fake_gemini_call(session_arg, user_request):
        raise RuntimeError("network blocked")

    def fake_post(url, json_payload, headers=None, timeout=None):
        assert url.endswith("/chat")
        return DummyResponse(json_data={"message": "Gateway fallback reply"})

    output = chat_via_gateway(
        session,
        "哈囉？",
        post_fn=fake_post,
        gemini_fn=fake_gemini_call,
    )
    assert output == "Gateway fallback reply"


def test_format_gemini_fastlane_response_formats_json_answer():
    text = _format_gemini_fastlane_response(
        '{"conclusion":"核心是生命周期映射錯位","point_1":"宏展開後型別生命週期失真","point_2":"測試未覆蓋特定呼叫序列","point_3":"修補方向是顯式生命週期與橋接約束"}'
    )
    assert "結論：" in text
    assert "1." in text
    assert "2." in text
    assert "3." in text


def test_format_gemini_fastlane_response_formats_structured_sections():
    text = _format_gemini_fastlane_response(
        '{"conclusion":"問題來自生命周期錯配","root_cause":"宏展開後 Rust 型別生命週期與 PyO3 橋接預期失配","why_it_passes":"靜態檢查只看 Rust 內部一致性，測試未覆蓋跨語言呼叫序列","fix_strategy":"顯式標註生命周期並收斂橋接生成規則"}'
    )
    assert "結論：" in text
    assert "根因：" in text
    assert "為何會漏過：" in text
    assert "修補策略：" in text


def test_coerce_long_gemini_answer_uses_second_pass_for_non_json():
    captured = {}

    def fake_second_pass(session, original_prompt, draft_answer):
        captured["draft"] = draft_answer
        return '{"conclusion":"短結論","root_cause":"短根因","why_it_passes":"短原因","fix_strategy":"短修補"}'

    text = _coerce_long_gemini_answer(
        session=PilotSession(provider="Gemini", model="gemini-2.5-flash", api_key="k"),
        user_request="x" * 1200,
        raw_text="這是一段沒有 JSON 的長回答",
        finish_reason="MAX_TOKENS",
        second_pass_fn=fake_second_pass,
    )
    assert "結論：短結論" in text
    assert captured["draft"] == "這是一段沒有 JSON 的長回答"

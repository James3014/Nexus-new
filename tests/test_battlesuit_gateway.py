import json
from types import SimpleNamespace
from unittest.mock import patch

from nexus.services.gateway import BattlesuitGateway


def test_gateway_uses_response_key_from_gemini_cli_json():
    cli_stdout = json.dumps(
        {
            "session_id": "test-session",
            "response": "```json\n{\"status\":\"PASS\",\"summary\":\"ok\"}\n```",
            "stats": {
                "models": {
                    "gemini-2.5-flash": {
                        "tokens": {
                            "total": 42,
                        }
                    }
                }
            },
        }
    )
    fake_proc = SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")

    gateway = BattlesuitGateway(project_root=".")
    with patch("nexus.services.gateway.subprocess.run", return_value=fake_proc):
        data, raw_output = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["status"] == "PASS"
    assert data["summary"] == "ok"
    assert data["tokens_used"] == 42

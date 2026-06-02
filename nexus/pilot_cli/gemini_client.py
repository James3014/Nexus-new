from typing import Any, Dict, List, Optional, Tuple
import json

from nexus.pilot_cli.fastlane_formatter import (
    build_fastlane_prompt,
    build_long_answer_compression_prompt,
    format_gemini_fastlane_response,
)
from nexus.pilot_cli.http_client import curl_request
from nexus.pilot_cli.session import PilotSession


LONG_INPUT_THRESHOLD = 200
LONG_INPUT_MAX_TOKENS = 1000


def gemini_endpoint(model: str, api_key: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )


def gemini_payload(user_request: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": build_fastlane_prompt(user_request, LONG_INPUT_THRESHOLD)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 450,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if len(user_request) > LONG_INPUT_THRESHOLD:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["maxOutputTokens"] = LONG_INPUT_MAX_TOKENS
        payload["generationConfig"]["responseSchema"] = {
            "type": "OBJECT",
            "properties": {
                "conclusion": {"type": "STRING"},
                "root_cause": {"type": "STRING"},
                "why_it_passes": {"type": "STRING"},
                "fix_strategy": {"type": "STRING"},
            },
            "required": [
                "conclusion",
                "root_cause",
                "why_it_passes",
                "fix_strategy",
            ],
            "propertyOrdering": [
                "conclusion",
                "root_cause",
                "why_it_passes",
                "fix_strategy",
            ],
        }
    return payload


def compress_long_gemini_answer(session: PilotSession, original_prompt: str, draft_answer: str) -> str:
    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": build_long_answer_compression_prompt(original_prompt, draft_answer)}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 400,
            "thinkingConfig": {"thinkingBudget": 0},
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "conclusion": {"type": "STRING"},
                    "root_cause": {"type": "STRING"},
                    "why_it_passes": {"type": "STRING"},
                    "fix_strategy": {"type": "STRING"},
                },
                "required": [
                    "conclusion",
                    "root_cause",
                    "why_it_passes",
                    "fix_strategy",
                ],
                "propertyOrdering": [
                    "conclusion",
                    "root_cause",
                    "why_it_passes",
                    "fix_strategy",
                ],
            },
        },
    }
    response = curl_request(
        gemini_endpoint(session.model or "gemini-2.5-flash", session.api_key),
        method="POST",
        json_payload=payload,
        headers={"Content-Type": "application/json"},
        timeout=15.0,
    )
    data = json.loads(response.text)
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates in compression pass")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned empty compression response")
    return text


def coerce_long_gemini_answer(
    session: PilotSession,
    user_request: str,
    raw_text: str,
    finish_reason: str,
) -> str:
    """[SIMPLIFIED] 僅保留純文字回傳。治理與正規化交由 SemanticAdapter。"""
    return raw_text


def chat_via_gemini_api(session: PilotSession, user_request: str) -> str:
    if not session.api_key:
        raise RuntimeError("Missing Gemini API key")

    response = curl_request(
        gemini_endpoint(session.model or "gemini-2.5-flash", session.api_key),
        method="POST",
        json_payload=gemini_payload(user_request),
        headers={"Content-Type": "application/json"},
        timeout=15.0,
    )
    # 此處解析 HTTP 封裝，不屬於治理判斷。
    raw_http_data = json.loads(response.text)
    candidates = raw_http_data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")

    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts).strip()
    return text

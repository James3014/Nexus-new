import json


def build_fastlane_prompt(user_request: str, long_input_threshold: int) -> str:
    if len(user_request) > long_input_threshold:
        return (
            "你是 Nexus Pilot CLI 的 Fast Lane 引擎。現在是長題快速壓縮分析模式。\n"
            "請把答案壓縮成 4 個欄位：結論、根因、為何會漏過、修補策略。\n"
            "請只輸出 JSON，不要 markdown，不要額外文字。\n"
            "每個欄位都要精煉但完整，能直接讓工程師採取下一步。\n"
            "不要寒暄、不要重述題目、不要 markdown 標題、不要假裝你真的跑過測試或看過真實 codebase；若內容屬推測，直接明說是推測。\n"
            "問題如下：\n"
            f"{user_request}"
        )
    return (
        "你是 Nexus Pilot CLI 的 Fast Lane 引擎。\n"
        "請用繁體中文、精煉回答，先給結論，再給必要重點。\n"
        "不要寒暄、不要重述題目。\n"
        f"問題如下：\n{user_request}"
    )


def build_long_answer_compression_prompt(original_prompt: str, draft_answer: str) -> str:
    return (
        "你是 Nexus Pilot CLI 的回答壓縮器。\n"
        "請根據原題與草稿答案，輸出嚴格 JSON。\n"
        "欄位只能有：conclusion, root_cause, why_it_passes, fix_strategy。\n"
        "每個欄位都要簡短完整，不要 markdown，不要額外文字。\n"
        f"原題：\n{original_prompt}\n\n"
        f"草稿答案：\n{draft_answer}"
    )


def format_gemini_fastlane_response(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception:
        return text

    conclusion = data.get("conclusion", "").strip()
    root_cause = data.get("root_cause", "").strip()
    why_it_passes = data.get("why_it_passes", "").strip()
    fix_strategy = data.get("fix_strategy", "").strip()
    point_1 = data.get("point_1", "").strip()
    point_2 = data.get("point_2", "").strip()
    point_3 = data.get("point_3", "").strip()

    parts = []
    if conclusion:
        parts.append(f"結論：{conclusion}")
    structured_sections = [
        ("根因", root_cause),
        ("為何會漏過", why_it_passes),
        ("修補策略", fix_strategy),
    ]
    named = [f"{label}：{value}" for label, value in structured_sections if value]
    if named:
        parts.append("\n\n".join(named))

    bullet_points = [point_1, point_2, point_3]
    numbered = [f"{idx}. {point}" for idx, point in enumerate(bullet_points, start=1) if point]
    if numbered and not named:
        parts.append("\n".join(numbered))
    return "\n\n".join(parts) if parts else text

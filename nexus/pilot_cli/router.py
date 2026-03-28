from dataclasses import dataclass


@dataclass
class RouteDecision:
    lane: str


def route_input(user_input: str) -> RouteDecision:
    normalized = user_input.lower()
    self_check_markers = (
        "self-check",
        "self check",
        "health check",
        "自檢",
        "檢查健康",
        "健康檢查",
    )
    self_heal_markers = (
        "self-heal",
        "self heal",
        "自修",
        "自癒",
        "自我修復",
    )
    battle_markers = (
        "fix this bug",
        "analyze this repo",
        "govern this project",
        "幫我修",
        "修這個 bug",
        "分析這個 repo",
    )
    if any(marker in normalized for marker in self_check_markers):
        return RouteDecision(lane="SELF_CHECK_PROMPT")
    if any(marker in normalized for marker in self_heal_markers):
        return RouteDecision(lane="SELF_HEAL_PROMPT")
    if any(marker in normalized for marker in battle_markers):
        return RouteDecision(lane="BATTLE_CONFIRM")
    return RouteDecision(lane="FAST")

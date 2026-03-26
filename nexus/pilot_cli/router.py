from dataclasses import dataclass


@dataclass
class RouteDecision:
    lane: str


def route_input(user_input: str) -> RouteDecision:
    normalized = user_input.lower()
    battle_markers = (
        "fix this bug",
        "analyze this repo",
        "govern this project",
        "幫我修",
        "修這個 bug",
        "分析這個 repo",
    )
    if any(marker in normalized for marker in battle_markers):
        return RouteDecision(lane="BATTLE_CONFIRM")
    return RouteDecision(lane="FAST")

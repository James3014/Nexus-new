"""P0/P1 mainchain route freeze + Planner-authoritative capability catalog.

ROUTING FREEZE: no new RouteMode, execution_topology product selectors,
third planner, or Online+Local shadow mainchain.

CapabilityPlanner remains the sole selection authority for capabilities
on the UnifiedRuntime / MainchainEntry path. CapabilitySelector (core/engine)
may only supply metadata — never the selected set for this path.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Mapping

from nexus.contracts.hybrid_route import RouteMode
from nexus.engine.capability_planner import default_capability_nodes
from nexus.services.capability_registry import (
    ESCALATE_ONLY,
    LOCAL_STAGE_CAPABILITIES,
    ONLINE_ARMOR_FLAG_CAPABILITIES,
    WIRED_REAL,
    WIRED_STUB,
    classify_gap,
    list_planner_capability_names,
)

# ---------------------------------------------------------------------------
# Frozen product surface (read-only historical contract; not expandable)
# ---------------------------------------------------------------------------

FROZEN_ROUTE_MODE_VALUES: frozenset[str] = frozenset(m.value for m in RouteMode)
FROZEN_ROUTE_MODE_NAMES: frozenset[str] = frozenset(m.name for m in RouteMode)

# Canonical defining path for RouteMode — any other ClassDef named RouteMode
# is a new product class and is blocked when a path is known.
FROZEN_ROUTE_MODE_DEFINING_PATHS: frozenset[str] = frozenset(
    {
        "nexus/contracts/hybrid_route.py",
    }
)

# LocalAssist + planner-owned topologies already on the mainchain surface.
FROZEN_EXECUTION_TOPOLOGIES: frozenset[str] = frozenset(
    {
        "single_local_model",
        "local_cascade",
        "local_committee_only",
        "localheal_pipeline",
        "cloud_with_local_assist",
        "local_only",
    }
)

ROUTE_MODE_KEYS: frozenset[str] = frozenset({"route_mode", "RouteMode"})
TOPOLOGY_KEYS: frozenset[str] = frozenset({"execution_topology"})

# Paths scanned for FREEZE surface (mainchain + related call sites).
MAINCHAIN_FREEZE_SCAN_PATHS: tuple[str, ...] = (
    "nexus/services/unified_runtime.py",
    "nexus/services/mainchain_entry.py",
    "nexus/services/capability_registry.py",
    "nexus/services/mainchain_route_freeze.py",
    "nexus/services/capability_evidence_bundle.py",
    "nexus/services/online_nexus_context.py",
    "nexus/services/gateway.py",
    "nexus/services/local_assist_service.py",
    "nexus/engine/pipeline_repair.py",
)

MAINCHAIN_AUTHORITY = "CapabilityPlanner"
ROUTE_AUTHORITY_FORBIDDEN = frozenset(
    {
        "CapabilitySelector",
        "provider",
        "model_name",
        "benchmark_arm",
        "third_registry",
    }
)

MAINCHAIN_STAGE_ORDER: tuple[str, ...] = (
    "MainchainEntry",
    "CapabilityPlanner",
    "HybridRouteDecision",  # optional metadata on route; not a second selector
    "shared_capability_evidence",
    "Local",
    "Online",
    "Verifier",
    "Claim_Delivery_Gate",
)


def _const_str(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _hit(
    kind: str,
    *,
    detail: str,
    lineno: int | None = None,
    col: int | None = None,
    value: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"kind": kind, "detail": detail}
    if lineno is not None:
        row["lineno"] = lineno
    if col is not None:
        row["col_offset"] = col
    if value is not None:
        row["value"] = value
    return row


def _check_route_mode_value(
    value: str | None,
    *,
    lineno: int | None,
    form: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if value not in FROZEN_ROUTE_MODE_VALUES:
        return _hit(
            "unknown_route_mode",
            detail=f"{form} uses unknown route_mode={value!r}",
            lineno=lineno,
            value=value,
        )
    return None


def _check_topology_value(
    value: str | None,
    *,
    lineno: int | None,
    form: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if value not in FROZEN_EXECUTION_TOPOLOGIES:
        return _hit(
            "unknown_execution_topology",
            detail=f"{form} uses unknown execution_topology={value!r}",
            lineno=lineno,
            value=value,
        )
    return None


def _scan_route_mode_class(
    node: ast.ClassDef,
    *,
    path: str | None,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    rel = (path or "").replace("\\", "/")
    if rel and rel not in FROZEN_ROUTE_MODE_DEFINING_PATHS:
        hits.append(
            _hit(
                "new_route_mode_class",
                detail=f"new RouteMode class definition outside frozen contract path: {rel or '<string>'}",
                lineno=getattr(node, "lineno", None),
            )
        )

    for item in node.body:
        name: str | None = None
        value: str | None = None
        lineno = getattr(item, "lineno", None)
        if isinstance(item, ast.Assign):
            for t in item.targets:
                if isinstance(t, ast.Name):
                    name = t.id
                    break
            value = _const_str(item.value)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            name = item.target.id
            value = _const_str(item.value)
        else:
            continue
        if name is None:
            continue
        # Skip dunder / private helpers
        if name.startswith("_"):
            continue
        if name not in FROZEN_ROUTE_MODE_NAMES:
            hits.append(
                _hit(
                    "new_route_mode_member",
                    detail=f"new RouteMode member {name!r}",
                    lineno=lineno,
                    value=name,
                )
            )
        if value is not None and value not in FROZEN_ROUTE_MODE_VALUES:
            hits.append(
                _hit(
                    "new_route_mode_value",
                    detail=f"new RouteMode value {value!r} on member {name!r}",
                    lineno=lineno,
                    value=value,
                )
            )
    return hits


def scan_source_ast(
    source_text: str,
    *,
    path: str | None = None,
) -> dict[str, Any]:
    """AST + frozen-contract scan of a single Python source string.

    Blocks:
    - new ``class RouteMode`` outside the frozen defining path
    - new RouteMode enum members / values
    - unknown ``route_mode=`` / dict / kwargs values
    - unknown ``execution_topology=`` / dict / kwargs values
    """
    hits: list[dict[str, Any]] = []
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        return {
            "ok": False,
            "hits": [
                _hit(
                    "syntax_error",
                    detail=str(exc),
                    lineno=getattr(exc, "lineno", None),
                )
            ],
            "routing_surface_changed": True,
            "path": path,
        }

    for node in ast.walk(tree):
        # New or extended RouteMode class
        if isinstance(node, ast.ClassDef) and node.name == "RouteMode":
            hits.extend(_scan_route_mode_class(node, path=path))

        # Call keywords: build(route_mode=...), f(execution_topology=...)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "route_mode":
                    h = _check_route_mode_value(
                        _const_str(kw.value),
                        lineno=getattr(kw, "lineno", None),
                        form="call_keyword",
                    )
                    if h:
                        hits.append(h)
                elif kw.arg == "execution_topology":
                    h = _check_topology_value(
                        _const_str(kw.value),
                        lineno=getattr(kw, "lineno", None),
                        form="call_keyword",
                    )
                    if h:
                        hits.append(h)

        # Assignments: route_mode = "..." / execution_topology = "..."
        if isinstance(node, ast.Assign):
            names: list[str] = []
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.append(t.id)
                elif isinstance(t, ast.Attribute):
                    names.append(t.attr)
                elif isinstance(t, ast.Tuple):
                    for elt in t.elts:
                        if isinstance(elt, ast.Name):
                            names.append(elt.id)
                        elif isinstance(elt, ast.Attribute):
                            names.append(elt.attr)
            val = _const_str(node.value)
            for name in names:
                if name == "route_mode":
                    h = _check_route_mode_value(
                        val, lineno=getattr(node, "lineno", None), form="assign"
                    )
                    if h:
                        hits.append(h)
                elif name == "execution_topology":
                    h = _check_topology_value(
                        val, lineno=getattr(node, "lineno", None), form="assign"
                    )
                    if h:
                        hits.append(h)

        # AnnAssign: route_mode: str = "..."
        if isinstance(node, ast.AnnAssign):
            name: str | None = None
            if isinstance(node.target, ast.Name):
                name = node.target.id
            elif isinstance(node.target, ast.Attribute):
                name = node.target.attr
            val = _const_str(node.value) if node.value is not None else None
            if name == "route_mode":
                h = _check_route_mode_value(
                    val, lineno=getattr(node, "lineno", None), form="ann_assign"
                )
                if h:
                    hits.append(h)
            elif name == "execution_topology":
                h = _check_topology_value(
                    val, lineno=getattr(node, "lineno", None), form="ann_assign"
                )
                if h:
                    hits.append(h)

        # Dict literals: {"route_mode": "...", "execution_topology": "..."}
        if isinstance(node, ast.Dict):
            for k_node, v_node in zip(node.keys, node.values):
                key = _const_str(k_node)
                if key is None:
                    continue
                val = _const_str(v_node)
                if key == "route_mode":
                    h = _check_route_mode_value(
                        val,
                        lineno=getattr(v_node, "lineno", None) if v_node else None,
                        form="dict",
                    )
                    if h:
                        hits.append(h)
                elif key == "execution_topology":
                    h = _check_topology_value(
                        val,
                        lineno=getattr(v_node, "lineno", None) if v_node else None,
                        form="dict",
                    )
                    if h:
                        hits.append(h)

    return {
        "ok": not hits,
        "hits": hits,
        "routing_surface_changed": bool(hits),
        "path": path,
        "frozen_route_modes": sorted(FROZEN_ROUTE_MODE_VALUES),
        "frozen_topologies": sorted(FROZEN_EXECUTION_TOPOLOGIES),
    }


def assert_no_forbidden_route_literals(source_text: str) -> dict[str, Any]:
    """Public freeze check for a single source string (AST + frozen contract)."""
    result = scan_source_ast(source_text)
    return {
        "ok": result["ok"],
        "hits": result["hits"],
        "routing_surface_changed": result["routing_surface_changed"],
    }


def scan_mainchain_paths_for_forbidden_routes(
    repo_root: str | Path,
    *,
    extra_paths: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Machine FREEZE scan over mainchain + related changed call-site paths."""
    root = Path(repo_root)
    paths = list(MAINCHAIN_FREEZE_SCAN_PATHS)
    if extra_paths:
        paths.extend(str(p) for p in extra_paths)
    file_hits: list[dict[str, Any]] = []
    scanned: list[str] = []
    for rel in paths:
        path = root / rel
        if not path.is_file():
            continue
        scanned.append(rel)
        text = path.read_text(encoding="utf-8")
        result = scan_source_ast(text, path=rel)
        if not result["ok"]:
            file_hits.append({"path": rel, "hits": result["hits"]})
    return {
        "ok": not file_hits,
        "scanned_paths": scanned,
        "file_hits": file_hits,
        "routing_surface_changed": bool(file_hits),
        "route_authority": MAINCHAIN_AUTHORITY,
        "frozen_route_modes": sorted(FROZEN_ROUTE_MODE_VALUES),
        "frozen_topologies": sorted(FROZEN_EXECUTION_TOPOLOGIES),
    }


def single_planner_decision_id(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Verify one planner decision id is shared across receipt surfaces."""
    root_id = str(receipt.get("planner_decision_id") or "")
    planner = receipt.get("planner") if isinstance(receipt.get("planner"), Mapping) else {}
    planner_id = str(planner.get("planner_decision_id") or "")
    ctx = receipt.get("context_trace") if isinstance(receipt.get("context_trace"), Mapping) else {}
    ctx_id = str(ctx.get("planner_decision_id") or "")
    bundle = (
        receipt.get("capability_evidence_bundle")
        if isinstance(receipt.get("capability_evidence_bundle"), Mapping)
        else {}
    )
    bundle_id = str(bundle.get("planner_decision_id") or "")

    ids = [x for x in (root_id, planner_id, ctx_id, bundle_id) if x]
    unique = sorted(set(ids))
    ok = bool(root_id) and len(unique) == 1
    mismatches: list[str] = []
    for item in receipt.get("capabilities") or []:
        if not isinstance(item, Mapping):
            continue
        row_id = str(item.get("planner_decision_id") or "")
        if row_id and row_id != root_id:
            mismatches.append(str(item.get("name") or "?"))
    if mismatches:
        ok = False
    return {
        "ok": ok and not mismatches,
        "planner_decision_id": root_id,
        "unique_ids": unique,
        "mismatched_capabilities": mismatches,
        "selection_authority": MAINCHAIN_AUTHORITY,
    }


def assert_selection_authority_is_planner(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Every capability receipt row must cite CapabilityPlanner as selection_source."""
    bad: list[str] = []
    for item in receipt.get("capabilities") or []:
        if not isinstance(item, Mapping):
            continue
        src = str(item.get("selection_source") or "")
        if src and src != MAINCHAIN_AUTHORITY:
            bad.append(f"{item.get('name')}:{src}")
    return {
        "ok": not bad,
        "bad_rows": bad,
        "selection_authority": MAINCHAIN_AUTHORITY,
    }


# Terminal classes for historical / union inventory rows.
TERMINAL_CLASSES: frozenset[str] = frozenset(
    {
        "CANONICAL_RUNTIME",
        "ALIAS_OF",
        "OFFLINE_ONLY",
        "EXPERIMENTAL_NOT_PROMOTED",
        "DEPRECATED",
        "NON_CAPABILITY_ARTIFACT",
    }
)

# Semantic alias map (SPXDRAC / legacy name → planner canonical).
# Only entries with verified same-role semantics — not pure string similarity.
ALIAS_TO_CANONICAL: dict[str, str] = {
    "hyper_sprint": "hyper",
    "swarm_multi_agent": "swarm",
    "mempalace": "mempalace_gate",
    "file_lock_security_gate": "file_lock",
    "forecast_pregate": "forecast_gate",
    "registry_skills_sync": "registry_sync",
    "learn_scheduler_service": "learn_scheduler",
    "nightshift_runner_service": "nightshift",
    "metabolism_resume": "metabolism",
    "sandbox_replay": "sandbox",
    "sandbox_runner": "sandbox",
    "research_and_source_discipline": "research",
    "direct_master_loop": "direct_mode",
    "benchmark_meta_opt": "meta_opt",
}

# Historical inventory PascalCase → snake aliases into union canonicals.
HISTORICAL_NAME_ALIASES: dict[str, str] = {
    "BattleSwarm": "battle_swarm",
    "ReflexLoop": "reflex_loop",
    "ASIConstraintExtractor": "asi_constraint_extractor",
    "MFPGate": "mfp_gate",
    "LLMJudgeProviders": "llm_judge_panel",
    "RecursiveRepairLoop": "repair_loop",
    "MemPalace": "mempalace_gate",
    "HyperSprint": "hyper",
    "SwarmMultiAgent": "swarm",
}

NON_CAPABILITY_PATH_PREFIXES: tuple[str, ...] = (
    "infrastructure/",
    "nexus/infrastructure/",
)
NON_CAPABILITY_NAMES: frozenset[str] = frozenset(
    {
        "DistLock",
        "RedisPool",
        "GuardedFetch",
        "SQLiteRetry",
        "GovernanceMetrics",
    }
)

HISTORICAL_INVENTORY_RELPATH = (
    "nexus_wiki_vault/02_Modules/nexus_能力盤點_2026-02-20後新增.md"
)


def list_spxdrac_capability_names() -> tuple[str, ...]:
    """Dynamic SPXDRAC surface names from core CapabilityRegistry (metadata only)."""
    from nexus.core.capability_registry import CapabilityRegistry

    reg = CapabilityRegistry()
    names = [str(c.name) for c in reg.list_all_capabilities()]
    return tuple(sorted(set(names)))


def resolve_alias(name: str) -> str:
    """Resolve ALIAS_TO_CANONICAL chain; raise on cycles."""
    seen: list[str] = []
    current = str(name or "").strip()
    while current in ALIAS_TO_CANONICAL:
        if current in seen:
            raise ValueError(f"alias_cycle:{'->'.join(seen + [current])}")
        seen.append(current)
        current = ALIAS_TO_CANONICAL[current]
    return current


def validate_alias_map() -> dict[str, Any]:
    """Ensure aliases are acyclic and targets are not aliases."""
    errors: list[str] = []
    for src, dst in ALIAS_TO_CANONICAL.items():
        if src == dst:
            errors.append(f"self_alias:{src}")
        try:
            final = resolve_alias(src)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if final in ALIAS_TO_CANONICAL:
            errors.append(f"alias_target_is_alias:{src}->{final}")
        if not final:
            errors.append(f"empty_alias_target:{src}")
    return {"ok": not errors, "errors": errors, "alias_count": len(ALIAS_TO_CANONICAL)}


def _pascal_to_snake(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s.lower().replace("-", "_").replace(" ", "_")


def _executor_for(name: str) -> str:
    if name in WIRED_REAL:
        return f"mainchain.real:{name}"
    if name in WIRED_STUB:
        return f"mainchain.stub:{name}"
    if name in LOCAL_STAGE_CAPABILITIES:
        return "LocalAssistService/LocalModelExecutor"
    if name in ONLINE_ARMOR_FLAG_CAPABILITIES:
        return "online_armor_flags"
    if name in ESCALATE_ONLY:
        return "escalate_only_offline"
    try:
        from nexus.core.capability_executor_registry import get_executor

        if get_executor(name) is not None:
            return f"capability_executor_registry:{name}"
    except Exception:
        pass
    return "explicit_skip_or_offline"


def _consumer_for(name: str) -> str:
    if name in {"artifact_gate", "claim_gate", "delivery_gate", "acceptance_check"}:
        return "postflight"
    if name in LOCAL_STAGE_CAPABILITIES:
        return "Local"
    if name in ESCALATE_ONLY:
        return "escalate_stage"
    return "preflight+Online"


def _trigger_for(name: str, default_state: str) -> str:
    if name in ESCALATE_ONLY:
        return "selected_and_failure_or_explicit_flag"
    if default_state == "required":
        return "planner_required"
    return "planner_selected"


def _maturity_runtime_eligible(maturity: str, *, gap_class: str, name: str) -> bool:
    """Runtime-eligible only for production/beta with a real physical path.

    Escalate-only without a physical executor is NOT runtime-eligible for the
    Final Gate real-executor bar (policy skip is still valid when untriggered).
    """
    m = (maturity or "").lower()
    if m in {"experimental", "deprecated", "legacy_alias", "unknown"}:
        return False
    if gap_class in {
        "A_missing_invoker",
        "B_stub_only",
        "C_not_in_prompt",
        "D_selected_not_executed",
    }:
        return False
    if gap_class != "F_wired_ok" and name not in LOCAL_STAGE_CAPABILITIES:
        # E_escalate_ok without F means no physical executor when triggered.
        return False
    if m in {"production", "active", "beta", "ga", "routed"} or not m:
        return True
    # Free-form planner maturity: allow when F-wired.
    return gap_class == "F_wired_ok"


def load_historical_inventory_198(
    *,
    repo_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Parse the historical wiki inventory dynamically (no hard-coded count)."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    path = root / HISTORICAL_INVENTORY_RELPATH
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        rows.append(
            {
                "index": int(parts[0]),
                "name": parts[1].strip(),
                "path": parts[2].strip().strip("`"),
                "purpose": parts[3].strip(),
                "phase": parts[4].strip(),
                "wired": parts[5].strip(),
            }
        )
    return rows


def classify_historical_item(
    item: Mapping[str, Any],
    *,
    union_ids: set[str],
    canonical_ids: set[str],
) -> dict[str, Any]:
    """Assign exactly one terminal class to a historical inventory row."""
    name = str(item.get("name") or "")
    path = str(item.get("path") or "")
    wired = str(item.get("wired") or "")
    purpose = str(item.get("purpose") or "").lower()
    snake = _pascal_to_snake(name)

    if name in NON_CAPABILITY_NAMES or path.startswith("infrastructure/"):
        return {
            "historical_name": name,
            "terminal_class": "NON_CAPABILITY_ARTIFACT",
            "canonical_id": None,
            "snake": snake,
            "reason": "infrastructure_or_pool_primitive",
        }

    if "deprecated" in purpose or "deprecated" in path.lower():
        return {
            "historical_name": name,
            "terminal_class": "DEPRECATED",
            "canonical_id": None,
            "snake": snake,
            "reason": "deprecated_marker",
        }

    mapped = HISTORICAL_NAME_ALIASES.get(name)
    candidate = mapped or snake
    if candidate in ALIAS_TO_CANONICAL:
        final = resolve_alias(candidate)
        return {
            "historical_name": name,
            "terminal_class": "ALIAS_OF",
            "canonical_id": final,
            "snake": snake,
            "reason": "semantic_alias_map",
        }
    if candidate in canonical_ids or candidate in union_ids:
        final = resolve_alias(candidate) if candidate in ALIAS_TO_CANONICAL else candidate
        return {
            "historical_name": name,
            "terminal_class": "ALIAS_OF" if name != final else "CANONICAL_RUNTIME",
            "canonical_id": final,
            "snake": snake,
            "reason": "matches_union_canonical",
        }

    if "standalone" in wired or "❌" in wired:
        return {
            "historical_name": name,
            "terminal_class": "EXPERIMENTAL_NOT_PROMOTED",
            "canonical_id": None,
            "snake": snake,
            "reason": "standalone_not_on_mainchain",
        }

    return {
        "historical_name": name,
        "terminal_class": "OFFLINE_ONLY",
        "canonical_id": None,
        "snake": snake,
        "reason": "wired_module_not_planner_selected",
    }


def build_capability_catalog(
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """P1: Planner-authoritative catalog + SPXDRAC crosswalk + 198 classification.

    Counts are derived dynamically — never hard-coded 51/198.
    CapabilitySelector supplies metadata only; selection_authority is Planner.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    nodes = default_capability_nodes()
    planner_names = list(list_planner_capability_names())
    spxdrac_names = list(list_spxdrac_capability_names())
    planner_set = set(planner_names)
    spx_set = set(spxdrac_names)
    union_ids = sorted(planner_set | spx_set)

    alias_check = validate_alias_map()
    if not alias_check["ok"]:
        raise ValueError(f"alias_map_invalid:{alias_check['errors']}")

    reverse_aliases: dict[str, list[str]] = {}
    for src in ALIAS_TO_CANONICAL:
        final = resolve_alias(src)
        reverse_aliases.setdefault(final, []).append(src)

    rows: list[dict[str, Any]] = []
    alias_rows: list[dict[str, Any]] = []
    accounted: set[str] = set()

    for name in union_ids:
        if name in ALIAS_TO_CANONICAL:
            final = resolve_alias(name)
            alias_rows.append(
                {
                    "id": name,
                    "terminal_class": "ALIAS_OF",
                    "canonical_id": final,
                    "selection_authority": MAINCHAIN_AUTHORITY,
                    "selector_may_decide_route": False,
                    "source": "spxdrac" if name in spx_set else "planner",
                }
            )
            accounted.add(name)
            continue

        node = nodes.get(name)
        if node is not None:
            maturity = str(getattr(node, "maturity", "unknown") or "unknown")
            category = str(getattr(node, "category", "unknown") or "unknown")
            default_state = str(getattr(node, "default_state", "optional") or "optional")
            owner = f"capability_node:{category}"
            source = "planner+spxdrac" if name in spx_set else "planner"
        else:
            spx_info = None
            try:
                from nexus.core.capability_registry import CapabilityRegistry

                spx_info = CapabilityRegistry().get_capability(name)
            except Exception:
                spx_info = None
            maturity = str(getattr(spx_info, "maturity", "ACTIVE") or "ACTIVE")
            category = "spxdrac_metadata"
            default_state = "optional"
            owner = "spxdrac_capability_registry"
            source = "spxdrac"

        gap = classify_gap(name) if name in planner_set else "E_escalate_ok"
        aliases = sorted(set(reverse_aliases.get(name, [])))
        runtime_eligible = _maturity_runtime_eligible(maturity, gap_class=gap, name=name)
        if name not in planner_set:
            runtime_eligible = False

        rows.append(
            {
                "canonical_id": name,
                "aliases": aliases,
                "owner": owner,
                "trigger": _trigger_for(name, default_state),
                "executor": _executor_for(name),
                "consumer": _consumer_for(name),
                "maturity": maturity,
                "runtime_eligible": runtime_eligible,
                "selection_authority": MAINCHAIN_AUTHORITY,
                "category": category,
                "default_state": default_state,
                "gap_class": gap,
                "route_authority": MAINCHAIN_AUTHORITY,
                "selector_may_decide_route": False,
                "terminal_class": "CANONICAL_RUNTIME",
                "source": source,
                "spxdrac_ref": f"spxdrac:{name}" if name in spx_set else None,
                "legacy_inventory_ref": f"legacy_inventory:{name}",
            }
        )
        accounted.add(name)

    canonical_ids = {r["canonical_id"] for r in rows}
    for ar in alias_rows:
        target = ar["canonical_id"]
        if target not in canonical_ids:
            rows.append(
                {
                    "canonical_id": target,
                    "aliases": sorted(
                        s for s in ALIAS_TO_CANONICAL if resolve_alias(s) == target
                    ),
                    "owner": "alias_target_shell",
                    "trigger": "planner_selected",
                    "executor": _executor_for(target),
                    "consumer": _consumer_for(target),
                    "maturity": "unknown",
                    "runtime_eligible": target in planner_set,
                    "selection_authority": MAINCHAIN_AUTHORITY,
                    "category": "alias_target",
                    "default_state": "optional",
                    "gap_class": classify_gap(target),
                    "route_authority": MAINCHAIN_AUTHORITY,
                    "selector_may_decide_route": False,
                    "terminal_class": "CANONICAL_RUNTIME",
                    "source": "alias_target",
                    "spxdrac_ref": None,
                    "legacy_inventory_ref": f"legacy_inventory:{target}",
                }
            )
            canonical_ids.add(target)
            accounted.add(target)

    unaccounted_union = sorted(set(union_ids) - accounted)

    historical_raw = load_historical_inventory_198(repo_root=root)
    historical_classified: list[dict[str, Any]] = [
        classify_historical_item(
            item, union_ids=set(union_ids), canonical_ids=canonical_ids
        )
        for item in historical_raw
    ]
    unclassified_hist = [
        h for h in historical_classified if h.get("terminal_class") not in TERMINAL_CLASSES
    ]
    hist_class_counts: dict[str, int] = {c: 0 for c in sorted(TERMINAL_CLASSES)}
    for h in historical_classified:
        tc = str(h.get("terminal_class") or "")
        hist_class_counts[tc] = hist_class_counts.get(tc, 0) + 1

    dual_contract_note = {
        "CapabilityPlanner": "sole_mainchain_selection_authority",
        "CapabilitySelector": "spxdrac_metadata_only_not_mainchain_route",
        "core.capability_registry": "spxdrac_skill_registry_not_unified_runtime_router",
        "services.capability_registry": "mainchain_invoker_map_not_RouteMode",
    }

    scan = scan_mainchain_paths_for_forbidden_routes(root)
    surface_changed = bool(scan["routing_surface_changed"])
    scan_meta = {
        "scanned_paths": scan["scanned_paths"],
        "file_hits": scan["file_hits"],
        "ok": scan["ok"],
    }

    return {
        "schema": "nexus.mainchain_capability_catalog.v1",
        "route_authority": MAINCHAIN_AUTHORITY,
        "selection_authority": MAINCHAIN_AUTHORITY,
        "dual_contract_note": dual_contract_note,
        "mainchain_stage_order": list(MAINCHAIN_STAGE_ORDER),
        "planner_node_count": len(planner_names),
        "spxdrac_reference_count": len(spxdrac_names),
        "canonical_union_count": len(union_ids),
        "canonical_row_count": len(rows),
        "alias_row_count": len(alias_rows),
        "union_accounted_count": len(accounted),
        "union_unaccounted": unaccounted_union,
        "union_unaccounted_count": len(unaccounted_union),
        "alias_validation": alias_check,
        "legacy_inventory_reference_count": len(historical_raw),
        "legacy_inventory_classified_count": len(historical_classified),
        "legacy_inventory_unclassified_count": len(unclassified_hist),
        "legacy_inventory_class_counts": hist_class_counts,
        "routing_surface_changed": surface_changed,
        "routing_surface_scan": scan_meta,
        "new_topology_introduced": surface_changed,
        "new_route_mode_introduced": surface_changed,
        "rows": rows,
        "alias_rows": alias_rows,
        "historical_classifications": historical_classified,
    }


def freeze_summary(*, repo_root: str | Path | None = None) -> dict[str, Any]:
    """Summary of freeze contract. ``routing_surface_changed`` from real scan."""
    surface_changed = False
    scan_meta: dict[str, Any] = {}
    if repo_root is not None:
        scan = scan_mainchain_paths_for_forbidden_routes(repo_root)
        surface_changed = bool(scan["routing_surface_changed"])
        scan_meta = {
            "scanned_paths": scan.get("scanned_paths", []),
            "file_hits": scan.get("file_hits", []),
            "ok": scan.get("ok"),
        }
    else:
        # Attempt default repo root from this file location
        default_root = Path(__file__).resolve().parents[2]
        if (default_root / "nexus" / "services" / "mainchain_route_freeze.py").is_file():
            scan = scan_mainchain_paths_for_forbidden_routes(default_root)
            surface_changed = bool(scan["routing_surface_changed"])
            scan_meta = {
                "scanned_paths": scan.get("scanned_paths", []),
                "file_hits": scan.get("file_hits", []),
                "ok": scan.get("ok"),
                "repo_root": str(default_root),
            }
        else:
            scan_meta = {"note": "repo_root_unavailable"}

    return {
        "schema": "nexus.mainchain_route_freeze.v1",
        "route_authority": MAINCHAIN_AUTHORITY,
        "forbidden_authorities": sorted(ROUTE_AUTHORITY_FORBIDDEN),
        "mainchain_stage_order": list(MAINCHAIN_STAGE_ORDER),
        "frozen_route_modes": sorted(FROZEN_ROUTE_MODE_VALUES),
        "frozen_route_mode_names": sorted(FROZEN_ROUTE_MODE_NAMES),
        "frozen_topologies": sorted(FROZEN_EXECUTION_TOPOLOGIES),
        "routing_surface_changed": surface_changed,
        "routing_surface_scan": scan_meta,
    }

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple


@dataclass(frozen=True)
class ValidationError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def validate_plan(plan: Dict[str, Any], *, max_prompt_chars: int = 20_000) -> None:
    """Validate plan/subtasks structure.

    Expect (minimal):
      {"planId": str, "subtasks": [ {"id": str, "prompt": str, "routing": str, "dependsOn": [str]? } ] }

    This is intentionally minimal and permissive; you can extend later.
    """
    if not isinstance(plan, dict):
        raise ValidationError("plan must be an object")

    plan_id = plan.get("planId") or plan.get("id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ValidationError("planId is required")

    subtasks = plan.get("subtasks")
    if not isinstance(subtasks, list) or not subtasks:
        raise ValidationError("subtasks must be a non-empty list")

    ids: Set[str] = set()
    edges: List[Tuple[str, str]] = []

    for i, st in enumerate(subtasks):
        if not isinstance(st, dict):
            raise ValidationError(f"subtasks[{i}] must be an object")
        sid = st.get("id")
        if not isinstance(sid, str) or not sid.strip():
            raise ValidationError(f"subtasks[{i}].id is required")
        if sid in ids:
            raise ValidationError(f"duplicate subtask id: {sid}")
        ids.add(sid)

        routing = st.get("routing")
        if routing is not None and (not isinstance(routing, str) or not routing.strip()):
            raise ValidationError(f"subtasks[{i}].routing must be a non-empty string when provided")

        prompt = st.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValidationError(f"subtasks[{i}].prompt is required")
        if len(prompt) > max_prompt_chars:
            raise ValidationError(f"subtasks[{i}].prompt too long: {len(prompt)} > {max_prompt_chars}")

        deps = st.get("dependsOn") or []
        if not isinstance(deps, list):
            raise ValidationError(f"subtasks[{i}].dependsOn must be a list")
        for d in deps:
            if not isinstance(d, str) or not d.strip():
                raise ValidationError(f"subtasks[{i}].dependsOn contains invalid id")
            edges.append((sid, d))

    # validate dependsOn references
    for a, b in edges:
        if b not in ids:
            raise ValidationError(f"subtask {a} dependsOn unknown id: {b}")

    # DAG cycle check
    _assert_dag(ids, edges)


def _assert_dag(nodes: Set[str], edges: List[Tuple[str, str]]) -> None:
    # edges are (node -> depends_on)
    forward: Dict[str, List[str]] = {n: [] for n in nodes}
    indeg: Dict[str, int] = {n: 0 for n in nodes}

    # Convert to dependency graph: depends_on -> node for topo
    for node, dep in edges:
        forward[dep].append(node)
        indeg[node] += 1

    q = [n for n, d in indeg.items() if d == 0]
    seen = 0
    while q:
        cur = q.pop()
        seen += 1
        for nxt in forward[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)

    if seen != len(nodes):
        raise ValidationError("dependsOn has a cycle (DAG check failed)")

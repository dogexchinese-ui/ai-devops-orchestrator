from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import db as dbm
from .schema import validate_plan


def enqueue_plan(
    con,
    plan: Dict[str, Any],
    *,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> str:
    """Insert plan + subtasks into DB.

    Idempotency: if idempotency_key is provided and already exists, return existing plan id.
    """

    validate_plan(plan)

    plan_id = plan.get("planId") or plan.get("id")
    title = plan.get("title")

    now = dbm.now_ts()

    with dbm.tx_immediate(con):
        if idempotency_key:
            row = con.execute(
                "SELECT id FROM tasks WHERE idempotency_key=? AND kind='plan'",
                (idempotency_key,),
            ).fetchone()
            if row:
                return str(row["id"])

        con.execute(
            """
            INSERT INTO tasks(id, kind, plan_id, title, status, max_attempts, idempotency_key, created_at, updated_at)
            VALUES(?, 'plan', ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (plan_id, plan_id, title, max_attempts, idempotency_key, now, now),
        )

        for st in plan["subtasks"]:
            sid = st["id"]
            routing = st.get("routing")
            prompt = st.get("prompt")
            con.execute(
                """
                INSERT INTO tasks(id, kind, plan_id, title, routing, prompt, status, max_attempts, created_at, updated_at)
                VALUES(?, 'subtask', ?, ?, ?, ?, 'queued', ?, ?, ?)
                """,
                (sid, plan_id, st.get("title"), routing, prompt, max_attempts, now, now),
            )

            for dep in (st.get("dependsOn") or []):
                con.execute(
                    "INSERT OR IGNORE INTO deps(task_id, depends_on) VALUES(?, ?)",
                    (sid, dep),
                )

        con.execute(
            "INSERT INTO events(task_id, ts, level, message, data) VALUES(?,?,?,?,?)",
            (plan_id, now, "info", "enqueued plan", json.dumps({"subtasks": len(plan["subtasks"])}, ensure_ascii=False)),
        )

    return str(plan_id)


def next_runnable_task(con) -> Optional[dict]:
    """Find one runnable subtask: queued and all deps succeeded."""

    # Note: simple query; you can optimize later.
    row = con.execute(
        """
        SELECT t.*
        FROM tasks t
        WHERE t.kind='subtask'
          AND t.status='queued'
          AND NOT EXISTS (
            SELECT 1
            FROM deps d
            JOIN tasks td ON td.id = d.depends_on
            WHERE d.task_id = t.id
              AND td.status != 'succeeded'
          )
        ORDER BY t.created_at ASC
        LIMIT 1
        """
    ).fetchone()

    return dict(row) if row else None


def refresh_blocked_and_plans(con) -> None:
    """Best-effort state reconciliation.

    1) If a queued subtask depends on a terminal-failed dependency, mark it blocked.
    2) Recompute each plan status from its subtasks.
    """

    now = dbm.now_ts()

    # 1) blocked subtasks
    rows = con.execute(
        """
        SELECT t.id AS task_id
        FROM tasks t
        WHERE t.kind='subtask'
          AND t.status='queued'
          AND EXISTS (
            SELECT 1
            FROM deps d
            JOIN tasks td ON td.id = d.depends_on
            WHERE d.task_id = t.id
              AND td.status IN ('failed','blocked','canceled')
          )
        """
    ).fetchall()

    for r in rows:
        tid = r["task_id"]
        con.execute(
            "UPDATE tasks SET status='blocked', blocked_reason='dependency_failed', updated_at=? WHERE id=?",
            (now, tid),
        )
        con.execute(
            "INSERT INTO events(task_id, ts, level, message) VALUES(?,?,?,?)",
            (tid, now, "warn", "blocked: dependency_failed"),
        )

    # 2) recompute plan status
    plan_rows = con.execute("SELECT id FROM tasks WHERE kind='plan'").fetchall()
    for pr in plan_rows:
        plan_id = pr["id"]
        subt = con.execute(
            "SELECT status FROM tasks WHERE kind='subtask' AND plan_id=?",
            (plan_id,),
        ).fetchall()
        if not subt:
            continue

        statuses = [s["status"] for s in subt]
        if all(s == "succeeded" for s in statuses):
            new_status = "succeeded"
        elif any(s == "running" for s in statuses):
            new_status = "running"
        elif any(s == "queued" for s in statuses):
            new_status = "queued"
        elif any(s in ("failed", "blocked", "canceled") for s in statuses):
            new_status = "failed"
        else:
            new_status = "queued"

        old = con.execute("SELECT status FROM tasks WHERE id=?", (plan_id,)).fetchone()
        if old and old["status"] != new_status:
            con.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                (new_status, now, plan_id),
            )
            con.execute(
                "INSERT INTO events(task_id, ts, level, message) VALUES(?,?,?,?)",
                (plan_id, now, "info", f"plan status -> {new_status}"),
            )

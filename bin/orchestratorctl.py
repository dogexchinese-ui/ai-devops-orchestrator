#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

# Allow running from a checkout without installation
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from orchestrator import db as dbm
from orchestrator.queue import enqueue_plan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="orchestratorctl")
    ap.add_argument("--db", required=True)

    sub = ap.add_subparsers(dest="cmd", required=True)

    p_enqueue = sub.add_parser("enqueue")
    p_enqueue.add_argument("--plan", required=True, help="path to plan.json")
    p_enqueue.add_argument("--idempotency", default=None)
    p_enqueue.add_argument("--max-attempts", type=int, default=3)

    p_list = sub.add_parser("list")
    p_list.add_argument("--status", default=None)

    args = ap.parse_args(argv)

    con = dbm.connect(dbm.DbConfig(path=args.db))
    dbm.migrate(con)

    if args.cmd == "enqueue":
        plan = json.load(open(args.plan, "r", encoding="utf-8"))
        pid = enqueue_plan(con, plan, idempotency_key=args.idempotency, max_attempts=args.max_attempts)
        print(pid)
        return 0

    if args.cmd == "list":
        q = "SELECT id, kind, routing, status, attempt, max_attempts, updated_at FROM tasks"
        params = []
        if args.status:
            q += " WHERE status=?"
            params.append(args.status)
        q += " ORDER BY updated_at DESC LIMIT 100"
        rows = con.execute(q, params).fetchall()
        for r in rows:
            print(f"{r['id']}\t{r['kind']}\t{r['routing'] or ''}\t{r['status']}\t{r['attempt']}/{r['max_attempts']}\t{r['updated_at']}")
        return 0

    raise RuntimeError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())

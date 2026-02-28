from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from . import db as dbm
from .queue import next_runnable_task, refresh_blocked_and_plans
from .retry_policy import decide_retry


@dataclass
class DaemonConfig:
    db_path: str
    poll_seconds: float = 1.0
    runner_cmd: str = "bash -lc 'echo TODO runner for {task_id}; exit 1'"
    log_dir: str = "./logs"


def run_daemon(cfg: DaemonConfig) -> int:
    con = dbm.connect(dbm.DbConfig(path=cfg.db_path))
    dbm.migrate(con)

    os.makedirs(cfg.log_dir, exist_ok=True)

    stop = False

    def _sig(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    while not stop:
        refresh_blocked_and_plans(con)
        task = next_runnable_task(con)
        if not task:
            time.sleep(cfg.poll_seconds)
            continue

        task_id = task["id"]
        attempt = int(task.get("attempt", 0))
        max_attempts = int(task.get("max_attempts", 3))

        # claim
        with dbm.tx_immediate(con):
            row = con.execute("SELECT status, attempt FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["status"] != "queued":
                continue
            now = dbm.now_ts()
            con.execute(
                "UPDATE tasks SET status='running', attempt=attempt+1, updated_at=? WHERE id=?",
                (now, task_id),
            )
            con.execute(
                "INSERT INTO events(task_id, ts, level, message) VALUES(?,?,?,?)",
                (task_id, now, "info", f"claimed for run (attempt {attempt+1}/{max_attempts})"),
            )

        # run
        logfile = os.path.join(cfg.log_dir, f"{task_id}.attempt{attempt+1}.log")
        cmd = cfg.runner_cmd.format(
            task_id=task_id,
            routing=task.get("routing"),
            prompt=task.get("prompt"),
            db_path=cfg.db_path,
        )

        rc = _run_cmd(cmd, logfile)

        if rc == 0:
            _mark_succeeded(con, task_id)
        else:
            _mark_failed(con, task_id, failure_kind="agent", failure_detail=f"runner rc={rc}")
            # decide retry
            row = con.execute("SELECT attempt, max_attempts, failure_kind, failure_detail FROM tasks WHERE id=?", (task_id,)).fetchone()
            dec = decide_retry(
                failure_kind=row["failure_kind"],
                failure_detail=row["failure_detail"],
                attempt=int(row["attempt"]),
                max_attempts=int(row["max_attempts"]),
            )
            if dec.should_retry:
                with dbm.tx_immediate(con):
                    now = dbm.now_ts()
                    con.execute(
                        "UPDATE tasks SET status='queued', updated_at=? WHERE id=?",
                        (now, task_id),
                    )
                    con.execute(
                        "INSERT INTO events(task_id, ts, level, message) VALUES(?,?,?,?)",
                        (task_id, now, "warn", f"retry allowed: {dec.reason}"),
                    )
            else:
                with dbm.tx_immediate(con):
                    now = dbm.now_ts()
                    con.execute(
                        "INSERT INTO events(task_id, ts, level, message) VALUES(?,?,?,?)",
                        (task_id, now, "warn", f"no retry: {dec.reason}"),
                    )

        refresh_blocked_and_plans(con)

    return 0


def _run_cmd(cmd: str, logfile: str) -> int:
    with open(logfile, "wb") as f:
        p = subprocess.Popen(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT)
        return p.wait()


def _mark_succeeded(con, task_id: str) -> None:
    with dbm.tx_immediate(con):
        now = dbm.now_ts()
        con.execute(
            "UPDATE tasks SET status='succeeded', failure_kind=NULL, failure_detail=NULL, updated_at=? WHERE id=?",
            (now, task_id),
        )
        con.execute(
            "INSERT INTO events(task_id, ts, level, message) VALUES(?,?,?,?)",
            (task_id, now, "info", "succeeded"),
        )


def _mark_failed(con, task_id: str, *, failure_kind: str, failure_detail: str) -> None:
    with dbm.tx_immediate(con):
        now = dbm.now_ts()
        con.execute(
            "UPDATE tasks SET status='failed', failure_kind=?, failure_detail=?, updated_at=? WHERE id=?",
            (failure_kind, failure_detail, now, task_id),
        )
        con.execute(
            "INSERT INTO events(task_id, ts, level, message) VALUES(?,?,?,?)",
            (task_id, now, "error", f"failed: {failure_kind} ({failure_detail})"),
        )


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="sqlite db path")
    ap.add_argument("--poll", type=float, default=1.0)
    ap.add_argument("--runner", required=True, help="runner command template; supports {task_id} {routing} {prompt} {db_path}")
    ap.add_argument("--logs", default="./logs")
    args = ap.parse_args(argv)

    cfg = DaemonConfig(db_path=args.db, poll_seconds=args.poll, runner_cmd=args.runner, log_dir=args.logs)
    return run_daemon(cfg)


if __name__ == "__main__":
    raise SystemExit(main())

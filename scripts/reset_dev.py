"""Reset a development database and its Redis windows TOGETHER.

PostgreSQL and Redis hold two halves of a machine's state. Wiping only the tables leaves each machine's
window in Redis at its old last cycle, and the ordering rule then (correctly) ignores every new reading as
late. This script clears both, and verifies that nothing is left.

    python scripts/reset_dev.py --db monitor --redis-db 0 [--keep-machines 5,8,11]
"""
from __future__ import annotations

import argparse
import subprocess


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="monitor")
    ap.add_argument("--redis-db", default="0")
    ap.add_argument("--keep-machines", default="", help="comma-separated ids; other machines are deleted")
    a = ap.parse_args()
    sql = "truncate alerts, health_scores, readings; update machines set status = 'HEALTHY';"
    if a.keep_machines:
        sql += f" delete from machines where id not in ({','.join(str(int(x)) for x in a.keep_machines.split(','))});"
    subprocess.run(["psql", "-U", "postgres", "-h", "127.0.0.1", "-d", a.db, "-q", "-c", sql], check=True)
    # Python's split() also drops the carriage return redis-cli prints on Windows; a shell loop does not.
    keys = subprocess.run(["redis-cli", "-p", "6379", "-n", a.redis_db, "--raw", "keys", "window:*"], capture_output=True, text=True).stdout.split()
    if keys:
        subprocess.run(["redis-cli", "-p", "6379", "-n", a.redis_db, "del", *keys], check=True, capture_output=True)
    left = subprocess.run(["redis-cli", "-p", "6379", "-n", a.redis_db, "--raw", "keys", "window:*"], capture_output=True, text=True).stdout.split()
    assert not left, f"windows left in Redis: {left[:5]}"
    print(f"reset {a.db}: tables truncated, {len(keys)} Redis windows removed")


if __name__ == "__main__":
    main()

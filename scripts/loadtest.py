"""Stage 7 load test runner: start the service in one configuration, run k6 against POST /api/readings,
sample the service's own metrics while it runs, append one row to results/loadtest.csv.

    python scripts/loadtest.py --label before --pipeline direct --vus 50 --batch 1
    python scripts/loadtest.py --label after-pool --pipeline direct --vus 50 --batch 1 --env MONITOR_DB_POOL=40

Each run starts from an empty `monitor_load` database (readings, scores, alerts truncated, Redis windows cleared),
so every run measures fresh, in-order readings. The machine is a laptop: numbers are for comparison between runs.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / "service" / "target" / "service-0.1.0-SNAPSHOT.jar"
OUT = ROOT / "results" / "loadtest"
CSV = ROOT / "results" / "loadtest.csv"
DB = "monitor_load"
BASE = "http://localhost:8080"


def psql(sql: str, db: str = DB) -> str:
    return subprocess.run(["psql", "-U", "postgres", "-h", "127.0.0.1", "-d", db, "-tAq", "-c", sql],
                          capture_output=True, text=True, check=True).stdout.strip()


def reset() -> None:
    if psql(f"select 1 from pg_database where datname = '{DB}'", db="postgres") != "1":
        psql(f"create database {DB}", db="postgres")
    if psql("select to_regclass('public.readings')") == "readings":
        psql("truncate alerts, health_scores, readings; update machines set status = 'HEALTHY';")
    keys = subprocess.run(["redis-cli", "-p", "6379", "-n", "2", "--raw", "keys", "window:*"], capture_output=True, text=True).stdout.split()
    if keys:
        subprocess.run(["redis-cli", "-p", "6379", "-n", "2", "del", *keys], capture_output=True, check=True)


def metric(name: str, stat: str = "VALUE", tag: str = "") -> float | None:
    try:
        r = requests.get(f"{BASE}/actuator/metrics/{name}" + (f"?tag={tag}" if tag else ""), timeout=2)
        if r.status_code != 200:
            return None
        for m in r.json()["measurements"]:
            if m["statistic"] == stat:
                return float(m["value"])
    except requests.RequestException:
        return None
    return None


def sampler(stop: threading.Event, samples: list) -> None:
    while not stop.is_set():
        samples.append({
            "t": time.time(),
            "pending": metric("hikaricp.connections.pending"),
            "active": metric("hikaricp.connections.active"),
            "cpu": metric("process.cpu.usage"),
        })
        stop.wait(1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--pipeline", choices=["direct", "kafka"], default="direct")
    ap.add_argument("--vus", type=int, default=50)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--duration", default="60s")
    ap.add_argument("--env", action="append", default=[], help="extra KEY=VALUE for the service")
    ap.add_argument("--jvm", action="append", default=[], help="extra -D options for the service")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    reset()
    env = dict(os.environ, MONITOR_DB_URL=f"jdbc:postgresql://localhost:5432/{DB}", MONITOR_PIPELINE=a.pipeline,
               MONITOR_REDIS_DB="2")
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    topic = f"readings-load-{int(time.time())}"
    cmd = ["java", "-Dspring.data.redis.database=2", f"-Dmonitor.kafka.topic={topic}", f"-Dmonitor.kafka.group=load-{topic}",
           *[f"-D{j}" for j in a.jvm], "-jar", str(JAR)]
    log = open(OUT / f"{a.label}.service.log", "w")
    svc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(90):
            try:
                if requests.get(f"{BASE}/actuator/health", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("service did not start")
        stop, samples = threading.Event(), []
        th = threading.Thread(target=sampler, args=(stop, samples), daemon=True)
        th.start()
        summary_file = OUT / f"{a.label}.k6.json"
        k6 = subprocess.run(["k6", "run", "--quiet", "-e", f"VUS={a.vus}", "-e", f"BATCH={a.batch}", "-e", f"DURATION={a.duration}",
                             "-e", f"OUT={summary_file}", str(ROOT / "loadtest" / "ingest.js")], capture_output=True, text=True)
        stop.set()
        th.join()
        (OUT / f"{a.label}.k6.out").write_text(k6.stdout + k6.stderr)
        k = json.loads(summary_file.read_text())
        # drain: in kafka mode the processor keeps working after k6 stops
        t_end = time.time()
        stored = int(psql("select count(*) from readings"))
        for _ in range(600):
            if int(psql("select count(*) from health_scores")) >= stored:
                break
            time.sleep(1)
        drain_s = round(time.time() - t_end, 1)
        busy = [s for s in samples if s["pending"] is not None]
        row = {
            "label": a.label, "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pipeline": a.pipeline,
            "vus": a.vus, "batch": a.batch, "duration_s": k["duration_s"], "requests": k["requests"], "readings": k["readings"],
            "readings_per_s": round(k["readings_per_second"], 1), "p50_ms": round(k["p50_ms"], 2), "p95_ms": round(k["p95_ms"], 2),
            "p99_ms": round(k["p99_ms"], 2), "failed_rate": k["failed_rate"],
            "pool_pending_mean": round(sum(s["pending"] for s in busy) / max(len(busy), 1), 2),
            "pool_pending_max": max((s["pending"] for s in busy), default=0),
            "cpu_mean": round(sum(s["cpu"] or 0 for s in busy) / max(len(busy), 1), 3),
            "processing_ms_mean": round(1000 * (metric("monitor.processing.time", "TOTAL_TIME") or 0) / max(metric("monitor.processing.time", "COUNT") or 1, 1), 3),
            "inference_ms_mean": round(1000 * (metric("monitor.inference.time", "TOTAL_TIME") or 0) / max(metric("monitor.inference.time", "COUNT") or 1, 1), 3),
            "scored": int(psql("select count(*) from health_scores")), "stored": stored, "drain_s": drain_s,
            "settings": " ".join(a.env + a.jvm),
        }
        new = not CSV.exists()
        with CSV.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if new:
                w.writeheader()
            w.writerow(row)
        print(json.dumps(row, indent=2))
    finally:
        subprocess.run(["taskkill", "/PID", str(svc.pid), "/F"], capture_output=True)  # by PID only
        svc.wait(timeout=30)


if __name__ == "__main__":
    main()

"""Stage 4 "done when", end to end against a running service: replay engines of one split to failure
through the real ingest API and check that each produces exactly one WARNING and then one CRITICAL.

    python scripts/alert_replay.py --split val          # tune/inspect here
    python scripts/alert_replay.py --split test         # confirm once
    python scripts/alert_replay.py --split val --tag no-hysteresis   # with the service started under other alert settings

Needs: the service on --base (direct pipeline), psql and redis-cli on PATH (it resets the tables it checks),
and replayer/target/replayer.jar. Writes results/alert_replay_<split>[_<tag>].json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from data import load_split, load_train  # noqa: E402


def reset(db: str) -> None:
    sql = "truncate alerts, health_scores, readings; update machines set status = 'HEALTHY';"
    subprocess.run(["psql", "-U", "postgres", "-h", "127.0.0.1", "-d", db, "-q", "-c", sql], check=True)
    # KEYS, not --scan: the Windows build of redis-cli 5.0 returns nothing for --scan --pattern (found the hard way)
    keys = subprocess.run(["redis-cli", "-p", "6379", "--raw", "keys", "window:*"], capture_output=True, text=True).stdout.split()
    if keys:
        subprocess.run(["redis-cli", "-p", "6379", "del", *keys], check=True, capture_output=True)
    left = subprocess.run(["redis-cli", "-p", "6379", "--raw", "keys", "window:*"], capture_output=True, text=True).stdout.split()
    assert not left, f"reset left window keys behind: {left[:5]}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["val", "test"], required=True)
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--db", default="monitor")
    ap.add_argument("--rate", type=int, default=2000)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    units = load_split()[a.split]
    life = load_train().groupby("unit").cycle.max()
    total = int(life.loc[units].sum())
    reset(a.db)
    t0 = time.time()
    subprocess.run(["java", "-jar", str(ROOT / "replayer" / "target" / "replayer.jar"), "--file", str(ROOT / "data" / "raw" / "train_FD001.txt"),
                    "--units", ",".join(map(str, units)), "--rate", str(a.rate), "--url", a.base], check=True)
    # direct pipeline scores inside the request, but wait anyway in case the service runs the kafka pipeline
    for _ in range(120):
        scored = sum(len(requests.get(f"{a.base}/api/machines/{u}/health?limit=2000").json()["points"]) for u in units)
        if scored >= total:
            break
        time.sleep(1)
    alerts = requests.get(f"{a.base}/api/alerts?status=all&limit=1000").json()
    fleet = {m["id"]: m for m in requests.get(f"{a.base}/api/machines").json()}

    per_engine, passes = [], 0
    for u in units:
        mine = sorted([x for x in alerts if x["machineId"] == u], key=lambda x: (x["openedCycle"], x["id"]))
        sev = [x["severity"] for x in mine]
        ok = sev == ["WARNING", "CRITICAL"]
        passes += ok
        rec = {"unit": u, "life": int(life.loc[u]), "severities": sev, "pass": ok, "final_status": fleet[u]["status"],
               "alerts": [{"severity": x["severity"], "rule": x["rule"], "opened_cycle": x["openedCycle"],
                           "true_rul_at_open": int(life.loc[u]) - x["openedCycle"], "closed_cycle": x["closedCycle"]} for x in mine]}
        per_engine.append(rec)
    def lead(severity):
        vals = [al["true_rul_at_open"] for e in per_engine for al in e["alerts"] if al["severity"] == severity]
        return vals
    warn, crit = lead("WARNING"), lead("CRITICAL")
    summary = {
        "split": a.split, "tag": a.tag, "engines": len(units), "readings": total, "seconds": round(time.time() - t0, 1),
        "engines_passing": passes, "alerts_total": len(alerts),
        "warning_alerts": len(warn), "critical_alerts": len(crit),
        "mean_true_rul_at_warning": round(sum(warn) / len(warn), 1) if warn else None,
        "min_true_rul_at_warning": min(warn) if warn else None,
        "mean_true_rul_at_critical": round(sum(crit) / len(crit), 1) if crit else None,
        "min_true_rul_at_critical": min(crit) if crit else None,
        "engines_ending_critical": sum(e["final_status"] == "CRITICAL" for e in per_engine),
    }
    name = f"alert_replay_{a.split}" + (f"_{a.tag}" if a.tag else "")
    (ROOT / "results" / f"{name}.json").write_text(json.dumps({"summary": summary, "engines": per_engine}, indent=2))
    print(json.dumps(summary, indent=2))
    for e in per_engine:
        if not e["pass"]:
            print("FAIL", e["unit"], [(al["severity"], al["rule"], al["opened_cycle"], al["closed_cycle"]) for al in e["alerts"]])


if __name__ == "__main__":
    main()

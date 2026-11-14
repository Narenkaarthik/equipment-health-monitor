"""Stage 5 "done when": kill the processor mid-stream, restart it, and show that no reading is lost or
double-counted.

Setup: two service processes on the same PostgreSQL, Redis and Kafka.
  * ingest     (port 8080): monitor.pipeline=kafka, consumer disabled: validates, stores, publishes, returns.
  * processor  (port 8081): monitor.pipeline=kafka, consumer enabled: windows, model, alerts.
The replayer streams all 100 FD001 engines to ingest. Mid-stream the processor is killed hard
(taskkill /F by PID, no shutdown hooks: like a crash), left down for a while, then restarted.

Checks (results/restart_test.json):
  1. readings rows == lines in the file (ingest kept accepting while the processor was down);
  2. health_scores rows == readings rows, and every machine's scored cycles are exactly 1..life;
  3. every score equals the score of an uninterrupted reference (the simulator's prediction from the
     same window) within 1e-3: the window restored from Redis was the right one;
  4. every machine's alerts are identical to an uninterrupted simulation of the same engine (the restart
     changed no alert), and no machine has two open alerts of one severity;
  5. consumer lag ends at 0; redelivered messages after the restart were counted as LATE (idempotent).

Usage: python scripts/restart_test.py   (service jar built; Postgres, Redis, Kafka running)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
JAR = ROOT / "service" / "target" / "service-0.1.0-SNAPSHOT.jar"
RUN = ROOT / "results" / "logs"
KAFKA_BIN = Path(os.environ.get("KAFKA_HOME", "A:/tools/kafka_2.13-4.4.0")) / "bin" / "windows"


def sh(*cmd, check=True):
    return subprocess.run(list(cmd), capture_output=True, text=True, check=check)


def psql(sql: str) -> str:
    return sh("psql", "-U", "postgres", "-h", "127.0.0.1", "-d", "monitor", "-tAq", "-c", sql).stdout.strip()


def kafka(tool: str, *args) -> str:
    return sh("cmd", "/c", str(KAFKA_BIN / f"{tool}.bat"), *args, check=False).stdout


def start(name: str, port: int, consumer: bool, group: str, topic: str) -> subprocess.Popen:
    env = dict(os.environ, PORT=str(port), MONITOR_PIPELINE="kafka", MONITOR_CONSUMER_ENABLED=str(consumer).lower())
    log = open(RUN / f"restart-{name}.log", "a")
    p = subprocess.Popen(["java", f"-Dmonitor.kafka.group={group}", f"-Dmonitor.kafka.topic={topic}", "-jar", str(JAR)],
                         env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(90):
        try:
            if requests.get(f"http://localhost:{port}/actuator/health", timeout=1).status_code == 200:
                return p
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError(f"{name} did not start")


def kill(p: subprocess.Popen) -> None:
    sh("taskkill", "/PID", str(p.pid), "/F", check=False)  # by PID, never by image name
    p.wait(timeout=30)


def metric(port: int, name: str, tag: str = "") -> float:
    url = f"http://localhost:{port}/actuator/metrics/{name}" + (f"?tag={tag}" if tag else "")
    r = requests.get(url, timeout=5)
    return r.json()["measurements"][0]["value"] if r.status_code == 200 else 0.0


def lag(group: str, topic: str) -> int:
    out = kafka("kafka-consumer-groups", "--bootstrap-server", "localhost:9092", "--describe", "--group", group)
    total = 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[1] == topic and parts[5].isdigit():
            total += int(parts[5])
    return total


def reference_alerts(ref: dict[int, np.ndarray]) -> dict[int, list]:
    from alert_sim import service_rules, simulate
    from features import WINDOW

    rules = service_rules()
    return {u: [(a["severity"], a["rule"], a["opened_cycle"], a["closed_cycle"]) for a in
                simulate(pred, np.minimum(np.arange(1, len(pred) + 1), WINDOW), rules)] for u, pred in ref.items()}


def reference_scores() -> dict[int, np.ndarray]:
    import pickle

    from data import SENSORS, add_rul, load_train
    from features import WINDOW, build_feature_frame
    from train import checkpoint_path, truncated

    meta = json.loads((ROOT / "service" / "src" / "main" / "resources" / "models" / "rul.json").read_text())
    with open(checkpoint_path(meta["arm"], meta["seed"]), "rb") as f:
        model = truncated(pickle.load(f)["model"], meta["n_estimators"])
    out = {}
    for u, g in add_rul(load_train(), cap=None).groupby("unit"):
        X = build_feature_frame(g, SENSORS, WINDOW)[meta["feature_names"]].to_numpy()
        out[int(u)] = np.clip(model.predict(X.astype(np.float32).astype(np.float64)), 0, meta["cap"])
    return out


def main() -> None:
    RUN.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    group = f"processor-restart-{stamp}"
    # a fresh topic per run: never delete topics, Kafka on Windows shuts down when it cannot rename the
    # deleted topic's directory (AccessDeniedException; found the hard way)
    topic = f"readings-restart-{stamp}"
    # clean slate: tables and windows
    psql("truncate alerts, health_scores, readings; update machines set status = 'HEALTHY';")
    keys = sh("redis-cli", "-p", "6379", "--raw", "keys", "window:*").stdout.split()
    if keys:
        sh("redis-cli", "-p", "6379", "del", *keys)

    ingest = start("ingest", 8080, consumer=False, group=group, topic=topic)
    processor = start("processor", 8081, consumer=True, group=group, topic=topic)
    total = sum(1 for line in open(ROOT / "data" / "raw" / "train_FD001.txt") if line.strip())
    replay = subprocess.Popen(["java", "-jar", str(ROOT / "replayer" / "target" / "replayer.jar"), "--file",
                               str(ROOT / "data" / "raw" / "train_FD001.txt"), "--rate", "800", "--url", "http://localhost:8080"],
                              stdout=open(RUN / "restart-replayer.log", "w"), stderr=subprocess.STDOUT)
    timeline = []
    time.sleep(10)
    kill(processor)
    t_kill = time.time()
    # counted AFTER the kill: a count taken just before it misses the scores written while taskkill lands
    timeline.append({"event": "processor killed (taskkill /F)", "scored_so_far": int(psql("select count(*) from health_scores")),
                     "readings_so_far": int(psql("select count(*) from readings"))})
    time.sleep(8)
    down_scored = int(psql("select count(*) from health_scores"))
    timeline.append({"event": "after 8 s down", "scored": down_scored, "readings": int(psql("select count(*) from readings")),
                     "lag": lag(group, topic)})
    processor = start("processor", 8081, consumer=True, group=group, topic=topic)
    timeline.append({"event": "processor restarted", "seconds_down": round(time.time() - t_kill, 1)})
    replay.wait(timeout=600)
    for _ in range(300):
        if int(psql("select count(*) from health_scores")) >= total and lag(group, topic) == 0:
            break
        time.sleep(1)
    late_after_restart = metric(8081, "monitor.readings.processed", "outcome:late")

    readings = int(psql("select count(*) from readings"))
    scores = int(psql("select count(*) from health_scores"))
    per_machine = psql("select machine_id, count(*), min(cycle), max(cycle) from health_scores group by 1 order by 1")
    life = {}
    for line in open(ROOT / "data" / "raw" / "train_FD001.txt"):
        if line.strip():
            u, c = line.split()[:2]
            life[int(u)] = max(life.get(int(u), 0), int(c))
    contiguous = 0
    for line in per_machine.splitlines():
        m, n, lo, hi = map(int, line.split("|"))
        contiguous += (n == life[m] and lo == 1 and hi == life[m])

    ref = reference_scores()
    rows = psql("select machine_id, cycle, predicted_rul from health_scores order by machine_id, cycle")
    max_diff, n_cmp = 0.0, 0
    for line in rows.splitlines():
        m, c, v = line.split("|")
        max_diff = max(max_diff, abs(float(v) - ref[int(m)][int(c) - 1]))
        n_cmp += 1
    dup_open = int(psql("select count(*) from (select machine_id, severity from alerts where closed_at is null group by 1, 2 having count(*) > 1) t"))
    multi = int(psql("select count(*) from (select machine_id, severity from alerts group by 1, 2 having count(*) > 1) t"))
    service_alerts: dict[int, list] = {}
    for line in psql("select machine_id, severity, rule, opened_cycle, coalesce(closed_cycle, 0) from alerts order by machine_id, opened_cycle, id").splitlines():
        m, sev, rule, o, c = line.split("|")
        service_alerts.setdefault(int(m), []).append((sev, rule, int(o), int(c) or None))
    ref_alerts = reference_alerts(ref)
    alert_diff = [u for u in ref_alerts if ref_alerts[u] != service_alerts.get(u, [])]
    dlt = kafka("kafka-get-offsets", "--bootstrap-server", "localhost:9092", "--topic", topic + ".DLT")

    result = {
        "file_rows": total, "readings_rows": readings, "health_scores_rows": scores,
        "machines_scored_exactly_1_to_life": contiguous, "machines": len(life),
        "scores_compared_with_reference": n_cmp, "max_abs_diff_vs_reference": round(max_diff, 6),
        "machines_with_two_open_alerts_of_one_severity": dup_open,
        "machines_with_alerts_different_from_uninterrupted_run": len(alert_diff),
        "machines_with_repeated_alert_of_one_severity": multi,
        "note_repeated": "repeats also occur in the uninterrupted run: a property of the alert rule on those engines, not of the restart",
        "redelivered_and_ignored_as_late": int(late_after_restart),
        "topic": topic, "final_consumer_lag": lag(group, topic), "dead_letter_offsets": dlt.strip(),
        "timeline": timeline,
    }
    try:
        stats = requests.get("http://localhost:8081/actuator/metrics/monitor.processing.lag").json()
        result["processing_lag_max_ms"] = round(next(x["value"] for x in stats["measurements"] if x["statistic"] == "MAX") * 1000, 1)
    except Exception:  # noqa: BLE001
        pass
    result["passed"] = bool(readings == total and scores == total and contiguous == len(life) and max_diff < 1e-3
                            and dup_open == 0 and not alert_diff and result["final_consumer_lag"] == 0)
    (ROOT / "results" / "restart_test.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    kill(processor)
    kill(ingest)


if __name__ == "__main__":
    main()

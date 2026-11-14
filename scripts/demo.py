"""End-to-end demo with a verified prediction and a screenshot of it.

1. Reset the dev database and Redis together, keeping only the 15 held-out test engines.
2. Start the service (direct pipeline) and replay the test engines through the real ingest API, each up to
   cycle 200, so short-lived engines end red and long-lived ones are still green or amber.
3. Drive the dashboard in headless Edge (Playwright). Every wait is on a real network response or a real
   DOM state change, never on a virtual-time budget: the fleet request, the selected machine's health and
   sensor requests, and the alert list being filled by the live stream.
4. Exercise a prediction: the predicted RUL the dashboard shows for the selected machine must equal what
   the API returns and what the Python model predicts from the same 30-reading window (within display rounding).
5. Save showcase/demo_screenshot.png, showcase/demo_video.webm (Playwright's recording of the whole session)
   and results/demo_check.json.

    python scripts/demo.py [--unit 42] [--rate 150]
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
BASE = "http://localhost:8080"


def python_prediction(unit: int, cycle: int) -> float:
    from data import SENSORS, load_train
    from features import WINDOW, build_feature_frame
    from train import checkpoint_path, truncated

    meta = json.loads((ROOT / "service" / "src" / "main" / "resources" / "models" / "rul.json").read_text())
    with open(checkpoint_path(meta["arm"], meta["seed"]), "rb") as f:
        model = truncated(pickle.load(f)["model"], meta["n_estimators"])
    g = load_train()
    g = g[(g.unit == unit) & (g.cycle <= cycle)]
    X = build_feature_frame(g, SENSORS, WINDOW)[meta["feature_names"]].to_numpy()[-1:]
    return float(np.clip(model.predict(X.astype(np.float32).astype(np.float64))[0], 0, meta["cap"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, default=0, help="engine to show (default: the median-life test engine)")
    ap.add_argument("--rate", type=int, default=25, help="fleet-wide readings per second; 25 makes the video about two minutes")
    ap.add_argument("--max-cycles", type=int, default=200, help="stop every engine here, so long-lived engines are still healthy")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    split = json.loads((ROOT / "data" / "splits" / "fd001_split.json").read_text())
    units = split["test"]
    subprocess.run([sys.executable, str(ROOT / "scripts" / "reset_dev.py"), "--keep-machines", ",".join(map(str, units))], check=True)
    life = {}
    for line in open(ROOT / "data" / "raw" / "train_FD001.txt"):
        if line.strip():
            u, c = map(int, line.split()[:2])
            life[u] = max(life.get(u, 0), c)
    unit = a.unit or sorted(units, key=lambda u: life[u])[len(units) // 2]
    total = sum(min(life[u], a.max_cycles) for u in units)

    log = open(ROOT / "results" / "logs" / "demo-service.log", "w")
    svc = subprocess.Popen(["java", "-jar", str(ROOT / "service" / "target" / "service-0.1.0-SNAPSHOT.jar")],
                           env=dict(os.environ, MONITOR_PIPELINE="direct"), stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(90):
            try:
                if requests.get(f"{BASE}/actuator/health", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        video_dir = ROOT / "showcase" / "video_tmp"
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                                          record_video_dir=str(video_dir), record_video_size={"width": 1440, "height": 900})
            page = context.new_page()
            with page.expect_response(lambda r: r.url.endswith("/api/machines") and r.status == 200):
                page.goto(BASE + "/")
            page.wait_for_selector("#live.on", timeout=20000)  # the EventSource is open
            # watch the chosen engine live from its first reading (the video shows it going green to red)
            with page.expect_response(lambda r: f"/api/machines/{unit}/health" in r.url and r.status == 200, timeout=20000):
                page.click(f"tr.machine[data-id='{unit}']")
            replay = subprocess.Popen(["java", "-jar", str(ROOT / "replayer" / "target" / "replayer.jar"), "--file",
                                       str(ROOT / "data" / "raw" / "train_FD001.txt"), "--units", ",".join(map(str, units)),
                                       "--rate", str(a.rate), "--max-cycles", str(a.max_cycles), "--no-register"],
                                      stdout=open(ROOT / "results" / "logs" / "demo-replayer.log", "w"), stderr=subprocess.STDOUT)
            replay.wait(timeout=900)
            for _ in range(120):  # the service has scored every reading
                scored = sum(len(requests.get(f"{BASE}/api/machines/{u}/health?limit=2000").json()["points"]) for u in units)
                if scored >= total:
                    break
                time.sleep(1)
            # wait for the dashboard's own 5-second fleet refresh to bring the final state
            with page.expect_response(lambda r: r.url.endswith("/api/machines") and r.status == 200, timeout=15000):
                pass
            page.wait_for_timeout(1200)  # one 1-second render tick of the fleet table
            # select the engine: wait for its real health and sensor responses
            with page.expect_response(lambda r: f"/api/machines/{unit}/readings?sensor=s12" in r.url and r.status == 200, timeout=20000):
                page.click(f"tr.machine[data-id='{unit}']")
            page.wait_for_selector("#alertList li", timeout=20000)
            page.wait_for_timeout(500)  # Chart.js draws on the next animation frame (animation is off)
            shot = ROOT / "showcase" / "demo_screenshot.png"
            shot.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(shot), full_page=True)

            row_text = page.inner_text(f"tr.machine[data-id='{unit}']")
            shown = float(row_text.split()[-1])
            status_shown = row_text.split()[1].upper()
            alert_items = page.locator("#alertList li").count()
            video_path = Path(page.video.path())
            context.close()  # finalises the video file
            browser.close()
        video = ROOT / "showcase" / "demo_video.webm"
        video.unlink(missing_ok=True)
        video_path.replace(video)
        video_dir.rmdir()

        api_row = next(m for m in requests.get(f"{BASE}/api/machines").json() if m["id"] == unit)
        py = python_prediction(unit, api_row["lastCycle"])
        alerts = [x for x in requests.get(f"{BASE}/api/alerts?status=all").json() if x["machineId"] == unit]
        check = {
            "unit": unit, "last_cycle": api_row["lastCycle"], "life": life[unit],
            "dashboard_predicted_rul": shown, "api_predicted_rul": round(api_row["predictedRul"], 3), "python_predicted_rul": round(py, 3),
            "dashboard_equals_api": abs(shown - api_row["predictedRul"]) <= 0.05 + 1e-9,
            "api_equals_python": abs(api_row["predictedRul"] - py) < 1e-3,
            "status_shown": status_shown, "status_api": api_row["status"],
            "alerts_for_unit": [f"{x['severity']} at cycle {x['openedCycle']}" for x in alerts],
            "alert_items_on_page": alert_items, "model_version": api_row["modelVersion"],
        }
        check["passed"] = bool(check["dashboard_equals_api"] and check["api_equals_python"] and status_shown == api_row["status"])
        (ROOT / "results" / "demo_check.json").write_text(json.dumps(check, indent=2))
        print(json.dumps(check, indent=2))
    finally:
        subprocess.run(["taskkill", "/PID", str(svc.pid), "/F"], capture_output=True)  # by PID only
        svc.wait(timeout=30)


if __name__ == "__main__":
    main()

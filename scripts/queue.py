"""Resumable experiment queue. Runs every (arm, seed) fit and each arm's evaluation in order, skipping
fits whose checkpoint exists and runs whose run_id is already in results/runs.csv. Writes
results/status.json after every step so progress is visible from outside.

Launch detached with scripts/launch_detached.ps1 so it survives the end of an interactive session.
    python scripts/queue.py            # main experiment
    python scripts/queue.py --ablations  # post hoc ablations (model/ablations.py)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "results" / "status.json"
CONFIG = json.loads((ROOT / "model" / "config" / "experiment.json").read_text())
ARMS = list(CONFIG["arms"].keys())
SEEDS = CONFIG["seeds"]


def write_status(**kw) -> None:
    STATUS.parent.mkdir(exist_ok=True)
    kw["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    kw["pid"] = os.getpid()
    STATUS.write_text(json.dumps(kw, indent=2))


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run([sys.executable, *cmd], check=True, cwd=ROOT)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ablations", action="store_true")
    a = ap.parse_args()
    steps = []
    if not a.ablations:
        for arm in ARMS:
            for s in SEEDS:
                steps.append(("fit", arm, s))
            steps.append(("evaluate", arm, None))
    else:
        steps.append(("ablations", None, None))
    t0 = time.time()
    for i, (kind, arm, seed) in enumerate(steps, start=1):
        write_status(state="running", step=i, of=len(steps), current=f"{kind} {arm} {'' if seed is None else 's' + str(seed)}",
                     elapsed_s=round(time.time() - t0))
        if kind == "fit":
            run(["model/train.py", "fit", "--arm", arm, "--seed", str(seed)])
        elif kind == "evaluate":
            run(["model/train.py", "evaluate", "--arm", arm])
        else:
            run(["model/ablations.py"])
    write_status(state="done", step=len(steps), of=len(steps), current="", elapsed_s=round(time.time() - t0))
    print("queue done")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        write_status(state="failed", error=str(e))
        raise

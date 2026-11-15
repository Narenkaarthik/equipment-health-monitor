"""Run every load-test configuration three times, interleaved (before, after, after-cache, kafka, then again),
so slow drift of the laptop (thermal, background tasks) spreads over all configurations instead of biasing one.

    python scripts/loadtest_all.py [--repeats 3]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = [
    ("before", "direct", ["--env", "MONITOR_DB_POOL=10", "--jvm", "monitor.ingest.cache-machines=false"]),
    ("after", "direct", ["--env", "MONITOR_DB_POOL=40", "--jvm", "monitor.ingest.cache-machines=false"]),
    ("after-cache", "direct", ["--env", "MONITOR_DB_POOL=40", "--jvm", "monitor.ingest.cache-machines=true"]),
    ("kafka", "kafka", ["--env", "MONITOR_DB_POOL=40", "--jvm", "monitor.ingest.cache-machines=true"]),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    a = ap.parse_args()
    for run in range(1, a.repeats + 1):
        for label, pipeline, extra in CONFIGS:
            print(f"--- {label} run {run}", flush=True)
            subprocess.run([sys.executable, str(ROOT / "scripts" / "loadtest.py"), "--label", label, "--pipeline", pipeline,
                            "--vus", "50", "--batch", "1", "--run", str(run), *extra], check=True, cwd=ROOT)


if __name__ == "__main__":
    main()

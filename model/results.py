"""The single results file. Every finished run appends exactly one row to results/runs.csv.
Tables, figures, numbers.tex and the README are generated from this file; nothing is hand-typed.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "runs.csv"

COLUMNS = [
    "run_id", "timestamp", "phase", "arm", "model", "seed", "window", "cap", "n_sensors", "n_features",
    "n_estimators", "val_rmse", "test_rmse", "test_mae", "test_nasa", "test_status_acc", "test_status_f1_macro",
    "test_critical_recall", "official_rmse", "official_nasa", "train_seconds", "infer_us_per_row", "config_hash", "notes",
]


def config_hash() -> str:
    text = (ROOT / "model" / "config" / "experiment.json").read_text()
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def existing_run_ids() -> set[str]:
    if not RUNS.exists():
        return set()
    with RUNS.open(newline="") as f:
        return {row["run_id"] for row in csv.DictReader(f)}


def append_run(row: dict) -> None:
    RUNS.parent.mkdir(exist_ok=True)
    new = not RUNS.exists()
    full = {c: row.get(c, "") for c in COLUMNS}
    full["timestamp"] = full["timestamp"] or datetime.now(timezone.utc).isoformat(timespec="seconds")
    full["config_hash"] = full["config_hash"] or config_hash()
    with RUNS.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(full)


def load_runs():
    import pandas as pd

    df = pd.read_csv(RUNS)
    return df


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))

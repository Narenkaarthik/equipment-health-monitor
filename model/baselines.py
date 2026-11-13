"""Block 2 baselines: the trivial predictor and a ridge regression, per arm. One row per run in results/runs.csv.

Run: python model/baselines.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from features import CONFIG, PROCESSED, WINDOW, feature_names, load_memmap  # noqa: E402
from metrics import all_metrics  # noqa: E402
from results import append_run, existing_run_ids  # noqa: E402

CAP = int(CONFIG["label"]["cap"])


def arm_columns(arm: str) -> tuple[list[str], list[int]]:
    arms = json.loads((ROOT / "data" / "splits" / "arms.json").read_text())
    meta = json.loads((PROCESSED / "meta.json").read_text())
    names = feature_names(arms[arm])
    idx = [meta["feature_names"].index(n) for n in names]
    return names, idx


def load_arm(arm: str):
    _, idx = arm_columns(arm)
    d = {}
    for split in ("train", "val", "test", "official_last"):
        d[f"{split}_X"] = np.ascontiguousarray(load_memmap(f"{split}_X")[:, idx])
        d[f"{split}_y"] = np.asarray(load_memmap(f"{split}_y"))
    return d


def record(run_id: str, phase: str, arm: str, model: str, seed, n_est, val_pred, test_pred, off_pred, d,
           train_seconds: float, infer_us: float, notes: str = "") -> dict:
    tm = all_metrics(d["test_y"], test_pred)
    off = all_metrics(np.minimum(d["official_last_y"], CAP), off_pred)
    row = {
        "run_id": run_id, "phase": phase, "arm": arm, "model": model, "seed": seed, "window": WINDOW, "cap": CAP,
        "n_sensors": d["train_X"].shape[1] // 3, "n_features": d["train_X"].shape[1], "n_estimators": n_est,
        "val_rmse": round(all_metrics(d["val_y"], val_pred)["rmse"], 4),
        "test_rmse": round(tm["rmse"], 4), "test_mae": round(tm["mae"], 4), "test_nasa": round(tm["nasa"], 4),
        "test_status_acc": round(tm["status_acc"], 4), "test_status_f1_macro": round(tm["status_f1_macro"], 4),
        "test_critical_recall": round(tm["critical_recall"], 4),
        "official_rmse": round(off["rmse"], 4), "official_nasa": round(off["nasa"], 4),
        "train_seconds": round(train_seconds, 3), "infer_us_per_row": round(infer_us, 3), "notes": notes,
    }
    append_run(row)
    return row


def main() -> None:
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    done = existing_run_ids()
    for arm in ("full21", "informative15", "reduced8"):
        d = load_arm(arm)
        # trivial: the mean capped RUL of the train rows
        run_id = f"baseline-trivial_mean-{arm}"
        if run_id not in done:
            t0 = time.perf_counter()
            mu = float(np.mean(d["train_y"]))
            tr = time.perf_counter() - t0
            const = lambda X: np.full(len(X), mu)  # noqa: E731
            row = record(run_id, "baseline", arm, "trivial_mean", "", 0, const(d["val_X"]), const(d["test_X"]),
                         const(d["official_last_X"]), d, tr, 0.0, f"predicts {mu:.2f}")
            print(run_id, "test_rmse", row["test_rmse"])
        # ridge, fixed alpha, no selection
        run_id = f"baseline-ridge-{arm}"
        if run_id not in done:
            t0 = time.perf_counter()
            m = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(d["train_X"], d["train_y"])
            tr = time.perf_counter() - t0
            t1 = time.perf_counter()
            tp = np.clip(m.predict(d["test_X"]), 0, CAP)
            us = (time.perf_counter() - t1) / len(tp) * 1e6
            row = record(run_id, "baseline", arm, "ridge", "", 0, np.clip(m.predict(d["val_X"]), 0, CAP), tp,
                         np.clip(m.predict(d["official_last_X"]), 0, CAP), d, tr, us, "alpha=1.0, standardised")
            print(run_id, "test_rmse", row["test_rmse"])


if __name__ == "__main__":
    main()

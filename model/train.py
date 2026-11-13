"""Block 3 main experiment: GradientBoosting RUL regressor per arm and seed, under the pre-registered recipe.

Two sub-commands so a queue can resume:
  python model/train.py fit --arm full21 --seed 0      # checkpoint + validation curve
  python model/train.py evaluate --arm full21          # select n_estimators on val, score test once per seed
  python model/train.py profile                        # time a short fit to extrapolate the full one

Every evaluate appends one row per seed to results/runs.csv.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from baselines import load_arm, record  # noqa: E402
from features import CONFIG  # noqa: E402
from metrics import rmse  # noqa: E402
from results import existing_run_ids  # noqa: E402

CHECKPOINTS = ROOT / "model" / "checkpoints"
CURVES = ROOT / "results" / "val_curves"
SELECTIONS = ROOT / "results" / "selections.json"
LOGS = ROOT / "results" / "logs"
CAP = int(CONFIG["label"]["cap"])
GRID = [100, 200, 300, 400, 500, 600, 700, 800]
MODEL = CONFIG["model"]


def make_model(seed: int, n_estimators: int | None = None):
    from sklearn.ensemble import GradientBoostingRegressor

    return GradientBoostingRegressor(
        loss=MODEL["loss"],
        learning_rate=MODEL["learning_rate"],
        n_estimators=n_estimators or MODEL["max_estimators"],
        max_depth=MODEL["max_depth"],
        subsample=MODEL["subsample"],
        min_samples_leaf=MODEL["min_samples_leaf"],
        random_state=seed,
    )


def checkpoint_path(arm: str, seed: int) -> Path:
    return CHECKPOINTS / f"{arm}-s{seed}.pkl"


def log_path(arm: str, seed: int) -> Path:
    # every log is named after its checkpoint
    return LOGS / f"{arm}-s{seed}.log"


def fit(arm: str, seed: int) -> None:
    ck = checkpoint_path(arm, seed)
    if ck.exists():
        print(f"{ck.name} exists; skipping fit")
        return
    d = load_arm(arm)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    CURVES.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    m = make_model(seed).fit(d["train_X"], d["train_y"])
    seconds = time.perf_counter() - t0
    curve = {}
    for i, pred in enumerate(m.staged_predict(d["val_X"]), start=1):
        if i in GRID:
            curve[i] = rmse(d["val_y"], np.clip(pred, 0, CAP))
    with open(ck, "wb") as f:
        pickle.dump({"model": m, "arm": arm, "seed": seed, "train_seconds": seconds, "n_features": d["train_X"].shape[1]}, f)
    (CURVES / f"{arm}-s{seed}.json").write_text(json.dumps({"arm": arm, "seed": seed, "val_rmse_by_n_estimators": curve,
                                                           "train_seconds": round(seconds, 2)}, indent=2))
    with open(log_path(arm, seed), "a") as f:
        f.write(f"fit arm={arm} seed={seed} train_rows={len(d['train_y'])} seconds={seconds:.1f} "
                f"val_curve={json.dumps(curve)}\n")
    print(f"fit {arm} seed {seed}: {seconds:.1f}s; val RMSE by n: " + ", ".join(f"{k}:{v:.3f}" for k, v in curve.items()))


def truncated(model, n: int):
    """A copy of the fitted model that uses only its first n trees (identical to refitting with n_estimators=n)."""
    import copy

    m = copy.deepcopy(model)
    m.estimators_ = m.estimators_[:n]
    m.n_estimators_ = n
    m.set_params(n_estimators=n)
    if hasattr(m, "train_score_"):
        m.train_score_ = m.train_score_[:n]
    return m


def select(arm: str) -> tuple[int, dict]:
    """Pre-registered rule: n_estimators with the lowest mean validation RMSE across seeds."""
    seeds = CONFIG["seeds"]
    curves = [json.loads((CURVES / f"{arm}-s{s}.json").read_text())["val_rmse_by_n_estimators"] for s in seeds]
    mean_curve = {n: float(np.mean([c[str(n)] for c in curves])) for n in GRID}
    best = min(GRID, key=lambda n: mean_curve[n])
    return best, mean_curve


def evaluate(arm: str, phase: str = "main") -> None:
    seeds = CONFIG["seeds"]
    for s in seeds:
        if not checkpoint_path(arm, s).exists():
            raise SystemExit(f"missing checkpoint for {arm} seed {s}; run fit first")
    n_best, mean_curve = select(arm)
    sel = json.loads(SELECTIONS.read_text()) if SELECTIONS.exists() else {}
    sel[arm] = {"n_estimators": n_best, "mean_val_rmse_by_n": mean_curve, "rule": CONFIG["selection_rule"]}
    SELECTIONS.write_text(json.dumps(sel, indent=2))
    done = existing_run_ids()
    d = load_arm(arm)
    for s in seeds:
        run_id = f"{phase}-gbr-{arm}-s{s}"
        if run_id in done:
            print(f"{run_id} already in runs.csv; skipping")
            continue
        with open(checkpoint_path(arm, s), "rb") as f:
            ck = pickle.load(f)
        m = truncated(ck["model"], n_best)
        val_pred = np.clip(m.predict(d["val_X"]), 0, CAP)
        t1 = time.perf_counter()
        test_pred = np.clip(m.predict(d["test_X"]), 0, CAP)  # the test split is read here, once per run
        us = (time.perf_counter() - t1) / len(test_pred) * 1e6
        off_pred = np.clip(m.predict(d["official_last_X"]), 0, CAP)
        row = record(run_id, phase, arm, "gbr", s, n_best, val_pred, test_pred, off_pred, d, ck["train_seconds"], us,
                     notes=f"selected n={n_best} by mean val RMSE over seeds {seeds}; checkpoint {checkpoint_path(arm, s).name}")
        with open(log_path(arm, s), "a") as f:
            f.write(f"evaluate run_id={run_id} n_estimators={n_best} val_rmse={row['val_rmse']} test_rmse={row['test_rmse']} "
                    f"official_rmse={row['official_rmse']}\n")
        print(f"{run_id}: n={n_best} val {row['val_rmse']} test {row['test_rmse']} official {row['official_rmse']}")


def profile() -> None:
    d = load_arm("full21")
    t0 = time.perf_counter()
    make_model(0, n_estimators=50).fit(d["train_X"], d["train_y"])
    dt = time.perf_counter() - t0
    print(f"50 trees on full21: {dt:.1f}s -> {MODEL['max_estimators']} trees about {dt * MODEL['max_estimators'] / 50:.0f}s per fit; "
          f"9 fits about {9 * dt * MODEL['max_estimators'] / 50 / 60:.1f} min (smaller arms are faster)")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit")
    f.add_argument("--arm", required=True)
    f.add_argument("--seed", type=int, required=True)
    e = sub.add_parser("evaluate")
    e.add_argument("--arm", required=True)
    e.add_argument("--phase", default="main")
    sub.add_parser("profile")
    a = ap.parse_args()
    if a.cmd == "fit":
        fit(a.arm, a.seed)
    elif a.cmd == "evaluate":
        evaluate(a.arm, a.phase)
    else:
        profile()


if __name__ == "__main__":
    main()

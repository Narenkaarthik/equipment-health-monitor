"""Post hoc ablations (phase=posthoc in runs.csv). Designed AFTER the main result showed reduced8
2.6 cycles worse than full21 (H1 rejected), to separate the recipe from the idea:
  * greedy8: 8 sensors chosen by greedy forward selection on the VALIDATION engines (a cheap
    HistGradientBoosting proxy picks the sensors, the recipe model is then trained as usual):
    does any 8-sensor set reach non-inferiority, or is 8 simply too few?
  * random 8-sensor subsets drawn from the informative sensors (is it "8 sensors" or "these 8"?)
  * the 8 WORST-ranked informative sensors (what the ranking is worth)
  * window size 10 and 60 (recipe: 30) for full21 and reduced8: does the gap depend on the window?
  * cap 100 and 150 (recipe: 125) for full21 and reduced8: does the gap depend on the label cap?
Window and cap rows are compared as a GAP within the same setting, never across settings,
because a different cap is a different target.
Same model, same budget (grid + selection rule), three seeds, same split; features rebuilt as needed.

Run: python model/ablations.py        (resumable; skips run ids already in results/runs.csv)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from baselines import record  # noqa: E402
from data import SENSORS, add_rul, load_official_test, load_split, load_train, split_frames  # noqa: E402
from features import CONFIG, build_feature_frame, feature_names  # noqa: E402
from metrics import rmse  # noqa: E402
from results import existing_run_ids  # noqa: E402
from train import GRID, make_model, truncated  # noqa: E402

CAP = int(CONFIG["label"]["cap"])
SEEDS = CONFIG["seeds"]
ARMS = json.loads((ROOT / "data" / "splits" / "arms.json").read_text())


def dataset(sensors: list[str], window: int, cap: int) -> dict:
    raw = add_rul(load_train(), cap=cap)
    frames = split_frames(raw, load_split())
    cols = feature_names(sensors)
    d = {}
    for k, f in frames.items():
        ff = build_feature_frame(f, sensors, window)
        d[f"{k}_X"] = ff[cols].to_numpy(dtype=np.float64)
        d[f"{k}_y"] = ff["rul"].to_numpy(dtype=np.float64)
    off, off_rul = load_official_test()
    ff = build_feature_frame(off, sensors, window)
    last = ff.groupby("unit").tail(1).sort_values("unit")
    d["official_last_X"] = last[cols].to_numpy(dtype=np.float64)
    d["official_last_y"] = off_rul.loc[last.unit.to_numpy()].to_numpy(dtype=np.float64)
    return d


def run_setting(name: str, sensors: list[str], window: int, cap: int, notes: str) -> None:
    done = existing_run_ids()
    ids = [f"posthoc-gbr-{name}-s{s}" for s in SEEDS]
    if all(i in done for i in ids):
        print(f"{name}: all seeds present; skipping")
        return
    d = dataset(sensors, window, cap)
    models, curves, secs = [], [], []
    for s in SEEDS:
        t0 = time.perf_counter()
        m = make_model(s).fit(d["train_X"], d["train_y"])
        secs.append(time.perf_counter() - t0)
        curve = {}
        for i, pred in enumerate(m.staged_predict(d["val_X"]), start=1):
            if i in GRID:
                curve[i] = rmse(d["val_y"], np.clip(pred, 0, cap))
        models.append(m)
        curves.append(curve)
    n_best = min(GRID, key=lambda n: float(np.mean([c[n] for c in curves])))
    for s, m, sec in zip(SEEDS, models, secs):
        run_id = f"posthoc-gbr-{name}-s{s}"
        if run_id in done:
            continue
        mt = truncated(m, n_best)
        tp = np.clip(mt.predict(d["test_X"]), 0, cap)
        vp = np.clip(mt.predict(d["val_X"]), 0, cap)
        op = np.clip(mt.predict(d["official_last_X"]), 0, cap)
        d2 = dict(d)
        d2["official_last_y"] = np.minimum(d["official_last_y"], cap)
        row = record(run_id, "posthoc", name, "gbr", s, n_best, vp, tp, op, d2, sec, 0.0, notes=notes, window=window, cap=cap)
        print(f"{run_id}: n={n_best} test_rmse={row['test_rmse']}")


def greedy8() -> list[str]:
    """Forward selection of 8 sensors by validation RMSE with a fast proxy model. Cached in results/greedy8.json."""
    path = ROOT / "results" / "greedy8.json"
    if path.exists():
        return json.loads(path.read_text())["selected"]
    from sklearn.ensemble import HistGradientBoostingRegressor

    d = dataset(ARMS["informative15"], CONFIG["window"]["size"], CAP)
    names = feature_names(ARMS["informative15"])
    selected: list[str] = []
    trace = []
    while len(selected) < 8:
        best = None
        for s in ARMS["informative15"]:
            if s in selected:
                continue
            cand = selected + [s]
            idx = [names.index(f) for f in feature_names(cand)]
            m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_depth=4, random_state=0)
            m.fit(d["train_X"][:, idx], d["train_y"])
            r = rmse(d["val_y"], np.clip(m.predict(d["val_X"][:, idx]), 0, CAP))
            if best is None or r < best[1]:
                best = (s, r)
        selected.append(best[0])
        trace.append({"added": best[0], "val_rmse": round(best[1], 4)})
        print(f"greedy step {len(selected)}: +{best[0]} val RMSE {best[1]:.3f}", flush=True)
    path.write_text(json.dumps({"selected": selected, "trace": trace, "proxy": "HistGradientBoostingRegressor(max_iter=300, lr=0.05, depth=4)",
                                "selected_on": "validation engines only"}, indent=2))
    return selected


def main() -> None:
    informative = ARMS["informative15"]
    reduced8 = ARMS["reduced8"]
    full = ARMS["full21"]
    settings = []
    g8 = sorted(greedy8(), key=lambda s: int(s[1:]))
    settings.append(("greedy8", g8, 30, CAP, f"ablation: 8 sensors by greedy forward selection on validation {g8}"))
    for w in (10, 60):
        settings.append((f"full21-w{w}", full, w, CAP, f"ablation: window {w} instead of 30"))
        settings.append((f"reduced8-w{w}", reduced8, w, CAP, f"ablation: window {w} instead of 30"))
    rng = np.random.default_rng(123)
    for k in range(3):
        subset = sorted(rng.choice(informative, size=8, replace=False).tolist(), key=lambda s: int(s[1:]))
        settings.append((f"random8-{k}", subset, 30, CAP, f"ablation: random 8 of the informative sensors {subset}"))
    ranked = list(ARMS["spearman_abs_rho_window_mean_vs_rul_train"].keys())
    worst8 = sorted(ranked[-8:], key=lambda s: int(s[1:]))
    settings.append(("worst8", worst8, 30, CAP, f"ablation: the 8 lowest-ranked informative sensors {worst8}"))
    for cap in (100, 150):
        settings.append((f"full21-cap{cap}", full, 30, cap, f"ablation: cap {cap} instead of 125"))
        settings.append((f"reduced8-cap{cap}", reduced8, 30, cap, f"ablation: cap {cap} instead of 125"))
    for name, sensors, w, cap, notes in settings:
        run_setting(name, sensors, w, cap, notes)
    run_rowsplit()


def run_rowsplit() -> None:
    """Methodological gap: the same model and budget, evaluated on a ROW-level random split of the train and
    validation engines (rows of one engine land on both sides), against the engine-level split the recipe uses.
    The test engines are not touched. The difference is the optimism a leaky split would have reported."""
    done = existing_run_ids()
    ids = [f"posthoc-gbr-full21-rowsplit-s{s}" for s in SEEDS]
    if all(i in done for i in ids):
        print("rowsplit: all seeds present; skipping")
        return
    sel = json.loads((ROOT / "results" / "selections.json").read_text())
    n = sel["full21"]["n_estimators"]  # same trees as the recipe model, no new selection
    raw = add_rul(load_train(), cap=CAP)
    split = load_split()
    pool = raw[raw.unit.isin(split["train"] + split["val"])]
    cols = feature_names(ARMS["full21"])
    ff = build_feature_frame(pool, ARMS["full21"], CONFIG["window"]["size"])
    X, y = ff[cols].to_numpy(dtype=np.float64), ff["rul"].to_numpy(dtype=np.float64)
    off = dataset(ARMS["full21"], CONFIG["window"]["size"], CAP)
    for s in SEEDS:
        run_id = f"posthoc-gbr-full21-rowsplit-s{s}"
        if run_id in done:
            continue
        rng = np.random.default_rng(s)
        mask = rng.random(len(y)) < 0.8
        t0 = time.perf_counter()
        m = make_model(s, n_estimators=n).fit(X[mask], y[mask])
        sec = time.perf_counter() - t0
        hp = np.clip(m.predict(X[~mask]), 0, CAP)
        d = {"train_X": X[mask], "val_y": y[~mask], "test_y": y[~mask], "official_last_y": np.minimum(off["official_last_y"], CAP)}
        op = np.clip(m.predict(off["official_last_X"]), 0, CAP)
        row = record(run_id, "posthoc", "full21-rowsplit", "gbr", s, n, hp, hp, op, d, sec, 0.0,
                     notes="methodology: row-level random 80/20 split of train+val engines (leaky); test_rmse is on held-out ROWS")
        print(f"{run_id}: leaky row-split RMSE {row['test_rmse']}")


if __name__ == "__main__":
    if "--rowsplit-only" in sys.argv:
        run_rowsplit()
    else:
        main()

"""Bug audit of the main result before it is written up. Writes results/audit_main.json.

Checks, in order:
 1. every checkpoint holds the arm and seed its file name says, with the arm's feature count;
 2. the arm's columns sliced from the 63-wide arrays equal features rebuilt from scratch on only
    that arm's sensors (catches a wrong column mapping);
 3. test RMSE recomputed from the checkpoint at the selected n_estimators equals runs.csv;
 4. full21 vs informative15: how far apart the predictions are, and whether any tree splits on a
    feature of a constant sensor (explains identical scores);
 5. where full21's importance goes: share on sensors outside reduced8 (explains the gap).
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from baselines import arm_columns, load_arm  # noqa: E402
from data import add_rul, load_split, load_train, split_frames  # noqa: E402
from features import CONFIG, WINDOW, build_feature_frame, feature_names  # noqa: E402
from metrics import rmse  # noqa: E402
from results import load_runs  # noqa: E402
from train import SELECTIONS, checkpoint_path, truncated  # noqa: E402

CAP = int(CONFIG["label"]["cap"])
ARMS = json.loads((ROOT / "data" / "splits" / "arms.json").read_text())


def main() -> None:
    out: dict = {"checkpoints": [], "column_mapping": {}, "recomputed": [], "notes": []}
    sel = json.loads(SELECTIONS.read_text())
    runs = load_runs().set_index("run_id")

    # 1 + 3
    for arm in ("full21", "informative15", "reduced8"):
        names, _ = arm_columns(arm)
        d = load_arm(arm)
        for s in CONFIG["seeds"]:
            with open(checkpoint_path(arm, s), "rb") as f:
                ck = pickle.load(f)
            m = ck["model"]
            ok = ck["arm"] == arm and ck["seed"] == s and m.n_features_in_ == len(names) == ck["n_features"]
            out["checkpoints"].append({"file": checkpoint_path(arm, s).name, "arm": ck["arm"], "seed": ck["seed"],
                                       "n_features_in": int(m.n_features_in_), "expected": len(names), "ok": bool(ok)})
            n = sel[arm]["n_estimators"]
            pred = np.clip(truncated(m, n).predict(d["test_X"]), 0, CAP)
            r = rmse(d["test_y"], pred)
            logged = float(runs.loc[f"main-gbr-{arm}-s{s}", "test_rmse"])
            out["recomputed"].append({"run_id": f"main-gbr-{arm}-s{s}", "recomputed": round(r, 4), "runs_csv": logged,
                                      "match": abs(round(r, 4) - logged) < 1e-3})

    # 2
    raw = add_rul(load_train(), cap=CAP)
    frames = split_frames(raw, load_split())
    for arm in ("informative15", "reduced8"):
        sensors = ARMS[arm]
        rebuilt = build_feature_frame(frames["test"], sensors, WINDOW)[feature_names(sensors)].to_numpy()
        sliced = load_arm(arm)["test_X"]
        out["column_mapping"][arm] = {"max_abs_diff": float(np.max(np.abs(rebuilt - sliced))), "shape": list(sliced.shape)}

    # 4
    d21, d15 = load_arm("full21"), load_arm("informative15")
    const = [s for s in ARMS["full21"] if s not in ARMS["informative15"]]
    const_idx = {i for i, nme in enumerate(feature_names(ARMS["full21"])) if nme.split("_")[0] in const}
    diffs, const_splits = [], 0
    for s in CONFIG["seeds"]:
        m21 = truncated(pickle.load(open(checkpoint_path("full21", s), "rb"))["model"], sel["full21"]["n_estimators"])
        m15 = truncated(pickle.load(open(checkpoint_path("informative15", s), "rb"))["model"], sel["informative15"]["n_estimators"])
        diffs.append(float(np.max(np.abs(m21.predict(d21["test_X"]) - m15.predict(d15["test_X"])))))
        for est in m21.estimators_.ravel():
            feats = est.tree_.feature
            const_splits += int(np.sum(np.isin(feats[feats >= 0], list(const_idx))))
    out["full21_vs_informative15"] = {"constant_sensors": const, "max_abs_prediction_diff_per_seed": diffs,
                                      "splits_on_constant_sensor_features": const_splits}

    # 5
    m21 = truncated(pickle.load(open(checkpoint_path("full21", 0), "rb"))["model"], sel["full21"]["n_estimators"])
    imp = m21.feature_importances_
    by_sensor: dict[str, float] = {}
    for i, nme in enumerate(feature_names(ARMS["full21"])):
        by_sensor[nme.split("_")[0]] = by_sensor.get(nme.split("_")[0], 0.0) + float(imp[i])
    ranked = sorted(by_sensor.items(), key=lambda kv: -kv[1])
    outside = {k: v for k, v in by_sensor.items() if k not in ARMS["reduced8"] and v > 0}
    out["full21_importance_by_sensor"] = {k: round(v, 4) for k, v in ranked}
    out["importance_share_outside_reduced8"] = round(sum(outside.values()), 4)
    out["top_sensors_outside_reduced8"] = [k for k, v in sorted(outside.items(), key=lambda kv: -kv[1])[:4]]

    out["all_ok"] = (all(c["ok"] for c in out["checkpoints"]) and all(r["match"] for r in out["recomputed"])
                     and all(v["max_abs_diff"] < 1e-9 for v in out["column_mapping"].values()))
    (ROOT / "results" / "audit_main.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("all_ok", "column_mapping", "full21_vs_informative15", "importance_share_outside_reduced8",
                                          "top_sensors_outside_reduced8", "full21_importance_by_sensor")}, indent=2))


if __name__ == "__main__":
    main()

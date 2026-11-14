"""Post hoc: how redundant is each 8-sensor set? Mean absolute pairwise correlation between the sensors' 30-cycle
window means on the TRAIN engines. A set whose sensors move together carries less information than its size suggests.

    python model/redundancy.py   -> results/redundancy.json
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from baselines import load_arm  # noqa: E402
from features import feature_names  # noqa: E402


def main() -> None:
    arms = json.loads((ROOT / "data" / "splits" / "arms.json").read_text())
    X = np.asarray(load_arm("full21")["train_X"])
    names = feature_names(arms["full21"])
    ranked = list(arms["spearman_abs_rho_window_mean_vs_rul_train"].keys())
    sets = {"reduced8": arms["reduced8"], "worst8": sorted(ranked[-8:], key=lambda s: int(s[1:])),
            "greedy8": json.loads((ROOT / "results" / "greedy8.json").read_text())["selected"],
            "informative15": arms["informative15"]}

    def mean_abs_corr(sensors):
        cols = [names.index(f"{s}_mean") for s in sensors]
        c = np.corrcoef(X[:, cols], rowvar=False)
        return float(np.mean([abs(c[i, j]) for i, j in itertools.combinations(range(len(cols)), 2)]))

    out = {k: round(mean_abs_corr(v), 3) for k, v in sets.items()}
    out["method"] = "mean |Pearson r| between the window means of every pair of sensors in the set, train engines"
    (ROOT / "results" / "redundancy.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

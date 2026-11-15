"""Post hoc: how uncertain are the gaps, given only 15 test engines?

The ± in the tables is the spread over training seeds, which only captures the model's own randomness. The larger
uncertainty is which engines happen to be in the test split. This script resamples the test ENGINES with replacement
(paired: the same resampled engines for both arms), recomputes each arm's RMSE averaged over its seeds, and reports a
95% percentile interval for the gap to the 21-sensor model.

Predictions come from the saved checkpoints for the main arms. The post hoc 8-sensor sets kept no checkpoints, so they
are refitted with the same seeds and tree counts; the refit must reproduce the test RMSE in results/runs.csv, which
proves it is the same model.

    python model/bootstrap.py   -> results/bootstrap.json
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from ablations import dataset  # noqa: E402
from baselines import load_arm  # noqa: E402
from features import CONFIG, load_memmap  # noqa: E402
from metrics import rmse  # noqa: E402
from results import load_runs  # noqa: E402
from train import SELECTIONS, checkpoint_path, make_model, truncated  # noqa: E402

CAP = int(CONFIG["label"]["cap"])
SEEDS = CONFIG["seeds"]
B = 10000
MARGIN = 1.0


def main_arm_predictions(arm: str) -> tuple[np.ndarray, np.ndarray]:
    n = json.loads(SELECTIONS.read_text())[arm]["n_estimators"]
    d = load_arm(arm)
    preds = []
    for s in SEEDS:
        with open(checkpoint_path(arm, s), "rb") as f:
            preds.append(np.clip(truncated(pickle.load(f)["model"], n).predict(d["test_X"]), 0, CAP))
    return np.array(preds), d["test_y"]


def posthoc_predictions(name: str, runs) -> tuple[np.ndarray, np.ndarray]:
    rows = runs[(runs.phase == "posthoc") & (runs.arm == name)].sort_values("seed")
    import ast

    note = rows.notes.iloc[0]
    sensors = ast.literal_eval(note[note.index("["):note.rindex("]") + 1])
    d = dataset(sensors, int(rows.window.iloc[0]), int(rows.cap.iloc[0]))
    preds = []
    for _, r in rows.iterrows():
        m = make_model(int(r.seed), n_estimators=int(r.n_estimators)).fit(d["train_X"], d["train_y"])
        p = np.clip(m.predict(d["test_X"]), 0, CAP)
        got = round(rmse(d["test_y"], p), 4)
        assert abs(got - r.test_rmse) < 1e-3, f"{name} seed {r.seed}: refit gives {got}, runs.csv has {r.test_rmse}"
        preds.append(p)
    print(f"{name}: refit reproduces runs.csv for seeds {rows.seed.astype(int).tolist()}")
    return np.array(preds), d["test_y"]


def main() -> None:
    runs = load_runs()
    unit = np.asarray(load_memmap("test_unit"))
    engines = np.unique(unit)
    rows_of = [np.where(unit == e)[0] for e in engines]
    cache = ROOT / "data" / "processed" / "bootstrap_preds.npz"  # gitignored; refits are deterministic
    if cache.exists():
        z = np.load(cache)
        arms = {a: (z[a], z["y"]) for a in ("full21", "reduced8", "greedy8", "worst8")}
    else:
        arms = {a: main_arm_predictions(a) for a in ("full21", "reduced8")}
        for name in ("greedy8", "worst8"):
            arms[name] = posthoc_predictions(name, runs)
        np.savez(cache, y=arms["full21"][1], **{a: p for a, (p, _) in arms.items()})
    y = arms["full21"][1]
    for a, (_, ya) in arms.items():
        assert np.array_equal(ya, y), f"{a}: test labels differ"
    sq = {a: (p - y) ** 2 for a, (p, _) in arms.items()}  # (seeds, rows)

    rng = np.random.default_rng(20241115)
    boot = {a: np.empty(B) for a in sq}
    for b in range(B):
        pick = np.concatenate([rows_of[i] for i in rng.integers(0, len(engines), len(engines))])
        for a, s in sq.items():
            boot[a][b] = np.mean(np.sqrt(s[:, pick].mean(axis=1)))  # RMSE per seed, averaged over seeds
    point = {a: float(np.mean(np.sqrt(s.mean(axis=1)))) for a, s in sq.items()}
    out = {"resampled": f"{len(engines)} test engines with replacement, paired across arms", "draws": B, "margin": MARGIN, "gaps": {}}
    for a in ("reduced8", "greedy8", "worst8"):
        g = boot[a] - boot["full21"]
        lo, hi = np.percentile(g, [2.5, 97.5])
        out["gaps"][a] = {"gap": round(point[a] - point["full21"], 3), "ci95_low": round(float(lo), 3), "ci95_high": round(float(hi), 3),
                          "share_of_draws_below_margin": round(float(np.mean(g < MARGIN)), 3),
                          "non_inferior_by_ci": bool(hi < MARGIN), "inferior_by_ci": bool(lo > MARGIN)}
    # is a chosen 8 better than the ranked 8? (negative = better than the ranking)
    out["vs_reduced8"] = {}
    for a in ("greedy8", "worst8"):
        g = boot[a] - boot["reduced8"]
        lo, hi = np.percentile(g, [2.5, 97.5])
        out["vs_reduced8"][a] = {"diff": round(point[a] - point["reduced8"], 3), "ci95_low": round(float(lo), 3),
                                 "ci95_high": round(float(hi), 3), "better_by_ci": bool(hi < 0)}
    lo, hi = np.percentile(boot["full21"], [2.5, 97.5])
    out["full21_rmse_ci95"] = [round(float(lo), 2), round(float(hi), 2)]
    seed_std = float(np.std([np.sqrt(s.mean()) for s in sq["full21"]], ddof=1))
    out["full21_seed_std"] = round(seed_std, 3)
    out["full21_ci_halfwidth_over_seed_std"] = round((hi - lo) / 2 / seed_std, 1)
    (ROOT / "results" / "bootstrap.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

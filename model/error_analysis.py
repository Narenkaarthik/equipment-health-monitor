"""Error analysis of the deployed model on the TEST engines (Block 5).

    python model/error_analysis.py sample     # confusion matrix, pick 36 misclassified rows, draw their trajectories
    (label error_analysis/labels.csv by hand, looking at error_analysis/samples_*.png)
    python model/error_analysis.py summarise  # group counts -> results/error_analysis.json, embeddings figure

"Misclassified" means the status the service derives from the prediction (HEALTHY / WARNING / CRITICAL, thresholds
60 and 30) differs from the status of the true capped RUL. Categories used when labelling by hand:
  ambiguous  - the error is 10 cycles or less: a small error that happens to cross a neighbouring boundary;
  mislabeled - the label itself is wrong. FD001 labels are exact cycle counts from a run-to-failure simulation, so
               the only possible source is the cap convention (rows with true RUL above 125);
  model      - a real model error, further described by a pattern seen in the trajectory plot: lagging (prediction
               stays high on an engine that fails fast), early (prediction falls ahead of the truth on a long-lived
               engine), jitter (a single-reading spike or step), plateau (piecewise-constant tree output stuck near 60).
The 36-row sample is taken largest error first within each confusion type, so it over-represents model errors on
purpose; population shares are computed over every misclassified row as well.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
import plotstyle  # noqa: E402
from baselines import load_arm  # noqa: E402
from features import load_memmap  # noqa: E402
from metrics import status_of  # noqa: E402
from train import checkpoint_path, truncated  # noqa: E402

OUT = ROOT / "error_analysis"
FIG = ROOT / "report" / "figures"
NAMES = np.array(["HEALTHY", "WARNING", "CRITICAL"])


def deployed():
    meta = json.loads((ROOT / "service" / "src" / "main" / "resources" / "models" / "rul.json").read_text())
    with open(checkpoint_path(meta["arm"], meta["seed"]), "rb") as f:
        return meta, truncated(pickle.load(f)["model"], meta["n_estimators"])


def frame() -> pd.DataFrame:
    meta, model = deployed()
    d = load_arm(meta["arm"])
    df = pd.DataFrame({"unit": np.asarray(load_memmap("test_unit")), "cycle": np.asarray(load_memmap("test_cycle")),
                       "true": d["test_y"], "pred": np.clip(model.predict(d["test_X"]), 0, meta["cap"])})
    life = df.groupby("unit").cycle.transform("max")
    df["true_uncapped"] = life - df.cycle
    df["t_status"] = NAMES[status_of(df.true)]
    df["p_status"] = NAMES[status_of(df.pred)]
    df["err"] = df.pred - df.true
    return df


def sample() -> None:
    plotstyle.apply()
    import matplotlib.pyplot as plt

    df = frame()
    cm = pd.crosstab(df.t_status, df.p_status).reindex(index=NAMES, columns=NAMES, fill_value=0)
    wrong = df[df.t_status != df.p_status].copy()
    confusions = wrong.groupby(["t_status", "p_status"]).size().sort_values(ascending=False)
    print("confusion matrix (rows true, columns predicted):\n", cm, "\n\nmost frequent confusions:\n", confusions)

    # 36 samples: per confusion type proportional to its frequency (min 2), largest |error| first, max 3 rows per engine
    picks = []
    per_type = {k: max(2, round(36 * v / len(wrong))) for k, v in confusions.items()}
    for (t, p), n in per_type.items():
        cand = wrong[(wrong.t_status == t) & (wrong.p_status == p)].assign(abserr=lambda x: x.err.abs()).sort_values("abserr", ascending=False)
        taken, per_engine = 0, {}
        for _, r in cand.iterrows():
            if taken >= n:
                break
            if per_engine.get(r.unit, 0) >= 3:
                continue
            # spread along the engine's life: skip a row within 8 cycles of one already taken from that engine
            if any(abs(r.cycle - q["cycle"]) < 8 for q in picks if q["unit"] == r.unit):
                continue
            picks.append(r.to_dict())
            per_engine[r.unit] = per_engine.get(r.unit, 0) + 1
            taken += 1
    s = pd.DataFrame(picks).reset_index(drop=True)
    s.insert(0, "sample", np.arange(1, len(s) + 1))
    OUT.mkdir(exist_ok=True)
    s[["sample", "unit", "cycle", "true", "true_uncapped", "pred", "err", "t_status", "p_status"]].round(2).to_csv(OUT / "samples.csv", index=False)
    cm.to_csv(OUT / "confusion_matrix.csv")

    # one panel per sample: the whole engine, true capped RUL, prediction, the sample marked
    for page in range(0, len(s), 12):
        chunk = s.iloc[page:page + 12]
        fig, axes = plt.subplots(3, 4, figsize=(12, 7.5), sharey=True)
        for ax, (_, r) in zip(axes.ravel(), chunk.iterrows()):
            e = df[df.unit == r.unit]
            ax.plot(e.cycle, e.true, color=plotstyle.INK_2, linewidth=1.2, label="true (capped)")
            ax.plot(e.cycle, e.pred, color=plotstyle.SERIES[0], linewidth=1.0, label="predicted")
            ax.axhline(60, color=plotstyle.STATUS["WARNING"], linewidth=0.8, linestyle="--")
            ax.axhline(30, color=plotstyle.STATUS["CRITICAL"], linewidth=0.8, linestyle="--")
            ax.plot([r.cycle], [r.pred], "o", color=plotstyle.SERIES[1], markersize=7)
            ax.set_title(f"#{int(r['sample'])} engine {int(r.unit)} cycle {int(r.cycle)}: {r.t_status[0]}->{r.p_status[0]}", fontsize=8)
        for ax in axes.ravel()[len(chunk):]:
            ax.axis("off")
        axes[0, 0].legend(fontsize=7)
        fig.tight_layout()
        plotstyle.save(fig, OUT / f"samples_{page // 12 + 1}")
    print(f"\n{len(s)} samples written to {OUT / 'samples.csv'}")


def summarise() -> None:
    plotstyle.apply()
    import matplotlib.pyplot as plt
    from sklearn.decomposition import PCA, TruncatedSVD
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    df = frame()
    s = pd.read_csv(OUT / "samples.csv")
    lab = pd.read_csv(OUT / "labels.csv")
    m = s.merge(lab, on="sample")
    assert len(m) == len(s) and m.category.isin(["ambiguous", "mislabeled", "model"]).all(), "every sample needs a category"
    cm = pd.read_csv(OUT / "confusion_matrix.csv", index_col=0)
    wrong = df[df.t_status != df.p_status]
    conf = wrong.groupby(["t_status", "p_status"]).size().sort_values(ascending=False)
    counts = m.category.value_counts().to_dict()
    out = {
        "population_small_error_share": round(float((wrong.err.abs() <= 10).mean()), 4),
        "population_misclassified_true_above_cap": int((wrong.true_uncapped > 125).sum()),
        "patterns": {k: int(v) for k, v in m.pattern.value_counts().items()},
        "test_rows": int(len(df)), "misclassified_rows": int(len(wrong)), "misclassified_share": round(len(wrong) / len(df), 4),
        "inspected": int(len(m)), "ambiguous": int(counts.get("ambiguous", 0)), "mislabeled": int(counts.get("mislabeled", 0)),
        "model": int(counts.get("model", 0)),
        "top_confusion": f"{conf.index[0][0]} predicted as {conf.index[0][1]}", "top_confusion_rows": int(conf.iloc[0]),
        "second_confusion": f"{conf.index[1][0]} predicted as {conf.index[1][1]}", "second_confusion_rows": int(conf.iloc[1]),
        "healthy_as_critical_rows": int(cm.loc["HEALTHY", "CRITICAL"]), "critical_as_healthy_rows": int(cm.loc["CRITICAL", "HEALTHY"]),
        "confusions": {f"{a}->{b}": int(v) for (a, b), v in conf.items()},
        "by_category_and_confusion": {f"{k[0]}|{k[1]}->{k[2]}": int(v) for k, v in m.groupby(["category", "t_status", "p_status"]).size().items()},
    }
    (ROOT / "results" / "error_analysis.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))

    # Embeddings: raw readings vs window features vs the model's leaf space, test rows, coloured by true capped RUL
    meta, model = deployed()
    from data import SENSORS, load_split, load_train, split_frames

    raw = split_frames(load_train(), load_split())["test"].sort_values(["unit", "cycle"])
    X_raw = StandardScaler().fit_transform(raw[[c for c in SENSORS if raw[c].std() > 1e-6]].to_numpy())
    d = load_arm(meta["arm"])
    X_win = StandardScaler().fit_transform(np.asarray(d["test_X"])[:, np.asarray(d["test_X"]).std(axis=0) > 1e-9])
    leaves = model.apply(d["test_X"]).reshape(len(d["test_X"]), -1)
    X_leaf = OneHotEncoder(handle_unknown="ignore").fit_transform(leaves)
    emb = [("raw readings (15 sensors), PCA", PCA(2, random_state=0).fit_transform(X_raw)),
           ("30-cycle window features, PCA", PCA(2, random_state=0).fit_transform(X_win)),
           ("model leaf space (200 trees), SVD", TruncatedSVD(2, random_state=0).fit_transform(X_leaf))]
    y = d["test_y"]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.3))
    for ax, (title, z) in zip(axes, emb):
        sc = ax.scatter(z[:, 0], z[:, 1], c=y, cmap="viridis_r", s=3, linewidths=0, rasterized=True)
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
    cb = fig.colorbar(sc, ax=axes, shrink=0.85, pad=0.01)
    cb.set_label("true RUL (capped at 125)")
    fig.suptitle("Test rows embedded before and after the method: health becomes one direction only after windowing and the model", fontsize=9.5, y=1.02)
    plotstyle.save(fig, FIG / "embeddings")

    # confusion matrix figure
    fig, ax = plt.subplots(figsize=(3.6, 3.0))
    mat = cm.to_numpy()
    ax.imshow(mat / mat.sum(axis=1, keepdims=True), cmap="Blues", vmin=0, vmax=1)
    for i in range(3):
        for j in range(3):
            share = mat[i, j] / mat[i].sum()
            ax.text(j, i, f"{mat[i, j]}\n{share:.0%}", ha="center", va="center", fontsize=8, color="white" if share > 0.6 else plotstyle.INK)
    ax.set_xticks(range(3), [n.lower() for n in NAMES], fontsize=8)
    ax.set_yticks(range(3), [n.lower() for n in NAMES], fontsize=8)
    ax.set_xlabel("predicted status")
    ax.set_ylabel("true status")
    ax.grid(False)
    ax.set_title("Status confusion on the test engines", fontsize=9)
    plotstyle.save(fig, FIG / "status_confusion")


if __name__ == "__main__":
    {"sample": sample, "summarise": summarise}[sys.argv[1]]()

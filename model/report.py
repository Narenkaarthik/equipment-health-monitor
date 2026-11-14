"""Everything derived from the results files: tables (Markdown + LaTeX), figures, report/numbers.tex macros,
results/numbers.json, and the README rendered from report/README.template.md. No number in any document is typed
by hand: documents read macros (LaTeX) or the numbers dict (Jinja templates).

Run: python model/report.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
import plotstyle  # noqa: E402
from features import CONFIG  # noqa: E402
from results import load_runs  # noqa: E402

REPORT = ROOT / "report"
FIG = REPORT / "figures"
TABLES = REPORT / "tables"
NUMBERS = REPORT / "numbers.tex"
NUMBERS_JSON = ROOT / "results" / "numbers.json"
MARGIN = 1.0

ARM_LABEL = {"full21": "all 21 sensors", "informative15": "15 informative sensors", "reduced8": "8 ranked sensors",
             "greedy8": "8 sensors, greedy on validation", "worst8": "8 lowest-ranked sensors", "random8": "8 random sensors"}
MODEL_LABEL = {"trivial_mean": "trivial (train mean)", "ridge": "ridge regression", "gbr": "gradient boosting"}
DIGITS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]


def macro_name(key: str) -> str:
    """LaTeX macro names cannot contain digits: spell each digit, then camel-case the words."""
    spelled = "".join(DIGITS[int(c)] if c.isdigit() else c for c in key)
    words = [w for w in re.split(r"[^A-Za-z]+", spelled) if w]
    return "".join(w[:1].upper() + w[1:] for w in words)


def tex_escape(s: str) -> str:
    return s.replace("\\", "\\textbackslash{}").replace("&", "\\&").replace("%", "\\%").replace("_", "\\_").replace("#", "\\#")


def fmt(x, nd=2) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "--"
    return f"{x:.{nd}f}".replace("-", "−")  # a real minus sign


def pm(m, s, nd=2) -> str:
    return f"{fmt(m, nd)} ± {fmt(s, nd)}"


def to_tex(df: pd.DataFrame, align: str) -> str:
    tex = df.to_latex(index=False, escape=False, column_format=align)
    return tex.replace("±", "$\\pm$").replace("−", "$-$")


def summarise(runs: pd.DataFrame) -> pd.DataFrame:
    g = runs.groupby(["phase", "arm", "model"], sort=False)
    agg = g.agg(
        n_runs=("run_id", "count"), n_sensors=("n_sensors", "first"), n_estimators=("n_estimators", "first"),
        window=("window", "first"), cap=("cap", "first"), val_rmse_mean=("val_rmse", "mean"),
        test_rmse_mean=("test_rmse", "mean"), test_rmse_std=("test_rmse", "std"),
        test_mae_mean=("test_mae", "mean"), test_mae_std=("test_mae", "std"),
        test_nasa_mean=("test_nasa", "mean"), test_nasa_std=("test_nasa", "std"),
        status_acc_mean=("test_status_acc", "mean"), status_f1_mean=("test_status_f1_macro", "mean"),
        critical_recall_mean=("test_critical_recall", "mean"),
        official_rmse_mean=("official_rmse", "mean"), official_rmse_std=("official_rmse", "std"),
        official_nasa_mean=("official_nasa", "mean"), train_seconds_mean=("train_seconds", "mean"),
    ).reset_index()
    return agg.fillna({"test_rmse_std": 0.0, "test_mae_std": 0.0, "test_nasa_std": 0.0, "official_rmse_std": 0.0})


def row(summary, phase, arm, model="gbr"):
    r = summary[(summary.phase == phase) & (summary.arm == arm) & (summary.model == model)]
    return None if r.empty else r.iloc[0]


# ---------------------------------------------------------------- tables
def main_table(summary):
    rows = []
    for phase, model, arm in [("baseline", "trivial_mean", "full21"), ("baseline", "ridge", "full21"), ("baseline", "ridge", "reduced8"),
                              ("main", "gbr", "full21"), ("main", "gbr", "informative15"), ("main", "gbr", "reduced8")]:
        r = row(summary, phase, arm, model)
        if r is None:
            continue
        rows.append({"Method": f"{MODEL_LABEL[model]}, {ARM_LABEL[arm]}", "Seeds": int(r.n_runs),
                     "Test RMSE": pm(r.test_rmse_mean, r.test_rmse_std), "Test MAE": pm(r.test_mae_mean, r.test_mae_std),
                     "NASA score": pm(r.test_nasa_mean, r.test_nasa_std), "Status acc.": fmt(r.status_acc_mean, 3),
                     "Macro-F1": fmt(r.status_f1_mean, 3), "CRITICAL recall": fmt(r.critical_recall_mean, 3),
                     "Official RMSE": pm(r.official_rmse_mean, r.official_rmse_std)})
    df = pd.DataFrame(rows)
    return df.to_markdown(index=False), to_tex(df, "l" + "r" * (len(df.columns) - 1))


def which8_table(summary, runs):
    full = row(summary, "main", "full21")
    rows = []
    for name, phase in [("full21", "main"), ("reduced8", "main"), ("greedy8", "posthoc"), ("worst8", "posthoc")]:
        r = row(summary, phase, name)
        if r is None:
            continue
        rows.append({"Sensor set": ARM_LABEL[name], "Chosen by": {"full21": "all", "reduced8": "pre-registered ranking (train)",
                                                                  "greedy8": "forward selection (validation)", "worst8": "bottom of the ranking"}[name],
                     "Test RMSE": pm(r.test_rmse_mean, r.test_rmse_std), "Gap to 21": fmt(r.test_rmse_mean - full.test_rmse_mean),
                     "Within 1.0": "" if name == "full21" else ("yes" if r.test_rmse_mean - full.test_rmse_mean < MARGIN else "no"),
                     "Phase": "pre-registered" if phase == "main" else "post hoc"})
    rnd = runs[runs.arm.str.startswith("random8-")]
    if len(rnd):
        m, s = rnd.test_rmse.mean(), rnd.test_rmse.std()
        rows.insert(3, {"Sensor set": f"{ARM_LABEL['random8']} ({rnd.arm.nunique()} draws)", "Chosen by": "random",
                        "Test RMSE": pm(m, s), "Gap to 21": fmt(m - full.test_rmse_mean),
                        "Within 1.0": "yes" if m - full.test_rmse_mean < MARGIN else "no", "Phase": "post hoc"})
    df = pd.DataFrame(rows)
    return df.to_markdown(index=False), to_tex(df, "llrrcl")


def recipe_table(summary):
    rows = []
    for label, a21, a8 in [("window 10", "full21-w10", "reduced8-w10"), ("window 30 (recipe)", "full21", "reduced8"),
                           ("window 60", "full21-w60", "reduced8-w60"), ("cap 100", "full21-cap100", "reduced8-cap100"),
                           ("cap 125 (recipe)", "full21", "reduced8"), ("cap 150", "full21-cap150", "reduced8-cap150")]:
        ph = "main" if a21 == "full21" else "posthoc"
        r21, r8 = row(summary, ph, a21), row(summary, ph, a8)
        if r21 is None or r8 is None:
            continue
        gap = r8.test_rmse_mean - r21.test_rmse_mean
        rows.append({"Setting": label, "21 sensors": pm(r21.test_rmse_mean, r21.test_rmse_std),
                     "8 ranked sensors": pm(r8.test_rmse_mean, r8.test_rmse_std), "Gap": fmt(gap),
                     "Within 1.0": "yes" if gap < MARGIN else "no"})
    df = pd.DataFrame(rows)
    return df.to_markdown(index=False), to_tex(df, "lrrrc")


def loadtest_table():
    p = ROOT / "results" / "loadtest.csv"
    if not p.exists():
        return "(no load test yet)", "% no load test yet", None
    lt = pd.read_csv(p)
    df = pd.DataFrame({"Run": lt.label, "Pipeline": lt.pipeline, "Users": lt.vus, "Batch": lt.batch,
                       "Readings/s": lt.readings_per_s.map(lambda v: fmt(v, 0)), "p50 ms": lt.p50_ms.map(fmt),
                       "p95 ms": lt.p95_ms.map(fmt), "p99 ms": lt.p99_ms.map(fmt), "Pool waits": lt.pool_pending_mean.map(fmt),
                       "Change": lt.settings.fillna("")})
    return df.to_markdown(index=False), to_tex(df.drop(columns=["Change"]), "llrrrrrrr"), lt


# ---------------------------------------------------------------- figures
def figures(summary, runs, lt):
    plotstyle.apply()
    import matplotlib.pyplot as plt

    # 1. main result
    order = [("baseline", "ridge", "full21"), ("baseline", "ridge", "reduced8"), ("main", "gbr", "full21"),
             ("main", "gbr", "informative15"), ("main", "gbr", "reduced8")]
    labels, means, stds, colors = [], [], [], []
    for phase, model, arm in order:
        r = row(summary, phase, arm, model)
        if r is None:
            continue
        labels.append(f"{MODEL_LABEL[model]}\n{ARM_LABEL[arm]}")
        means.append(r.test_rmse_mean)
        stds.append(r.test_rmse_std)
        colors.append(plotstyle.ARM_COLORS[arm] if model == "gbr" else plotstyle.GRID if False else plotstyle.SEQUENTIAL[0])
    triv = row(summary, "baseline", "full21", "trivial_mean")
    fig, ax = plt.subplots(figsize=(6.6, 3.0))
    x = np.arange(len(labels))
    ax.bar(x, means, color=colors, width=0.62, yerr=stds, capsize=3, error_kw={"elinewidth": 1, "ecolor": plotstyle.INK_2})
    for xi, m in zip(x, means):
        ax.text(xi, m + 0.6, fmt(m), ha="center", va="bottom", color=plotstyle.INK_2, fontsize=8)
    if triv is not None:
        ax.axhline(triv.test_rmse_mean, color=plotstyle.MUTED, linestyle="--", linewidth=1)
        ax.text(len(labels) - 0.5, triv.test_rmse_mean - 2.5, f"trivial baseline {fmt(triv.test_rmse_mean, 1)}", ha="right", color=plotstyle.MUTED, fontsize=8)
    ax.set_xticks(x, labels, fontsize=7.2)
    ax.set_ylabel("test RMSE (cycles), lower is better")
    ax.set_title("RUL error on 15 held-out engines (mean ± std over 3 seeds)")
    ax.set_ylim(0, (triv.test_rmse_mean if triv is not None else max(means)) * 1.08)
    plotstyle.save(fig, FIG / "main_test_rmse")

    # 2. which 8 sensors: every run as a dot, the margin as a band
    full = row(summary, "main", "full21")
    groups = [("8 ranked\n(pre-reg.)", runs[(runs.phase == "main") & (runs.arm == "reduced8")]),
              ("8 random", runs[runs.arm.str.startswith("random8-")]),
              ("8 worst-\nranked", runs[runs.arm == "worst8"]),
              ("8 greedy\n(validation)", runs[runs.arm == "greedy8"])]
    groups = [(n, g) for n, g in groups if len(g)]
    fig, ax = plt.subplots(figsize=(5.4, 2.9))
    ax.axhspan(full.test_rmse_mean, full.test_rmse_mean + MARGIN, color=plotstyle.SEQUENTIAL[0], alpha=0.25, linewidth=0)
    ax.axhline(full.test_rmse_mean, color=plotstyle.SERIES[0], linewidth=1.2)
    ax.text(len(groups) - 0.55, full.test_rmse_mean - 0.45, "all 21 sensors", color=plotstyle.SERIES[0], fontsize=7.5, ha="right")
    ax.text(len(groups) - 0.55, full.test_rmse_mean + MARGIN + 0.1, "non-inferiority margin", color=plotstyle.INK_2, fontsize=7.5, ha="right")
    for i, (name, g) in enumerate(groups):
        jitter = np.linspace(-0.12, 0.12, len(g)) if len(g) > 1 else [0]
        ax.scatter(i + np.asarray(jitter), g.test_rmse, s=22, color=plotstyle.SERIES[1] if i == 0 else plotstyle.SERIES[6], zorder=3)
        ax.plot([i - 0.2, i + 0.2], [g.test_rmse.mean()] * 2, color=plotstyle.INK, linewidth=1.5)
    ax.set_xticks(range(len(groups)), [n for n, _ in groups], fontsize=8)
    ax.set_xlim(-0.6, len(groups) - 0.4)
    ax.set_ylabel("test RMSE (cycles)")
    ax.set_title("It is which 8, not how many: every run (dots) and the mean (bar)", fontsize=9)
    plotstyle.save(fig, FIG / "which_eight")

    # 3. recipe sensitivity: gap across window and cap
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.6), sharey=True)
    for ax, (title, items) in zip(axes, [("window size", [(10, "full21-w10", "reduced8-w10"), (30, "full21", "reduced8"), (60, "full21-w60", "reduced8-w60")]),
                                         ("RUL cap", [(100, "full21-cap100", "reduced8-cap100"), (125, "full21", "reduced8"), (150, "full21-cap150", "reduced8-cap150")])]):
        xs, a21, a8 = [], [], []
        for xv, n21, n8 in items:
            ph = "main" if n21 == "full21" else "posthoc"
            r21, r8 = row(summary, ph, n21), row(summary, ph, n8)
            if r21 is None or r8 is None:
                continue
            xs.append(xv)
            a21.append(r21.test_rmse_mean)
            a8.append(r8.test_rmse_mean)
        ax.plot(xs, a21, marker="o", color=plotstyle.ARM_COLORS["full21"], label="21 sensors")
        ax.plot(xs, a8, marker="o", color=plotstyle.ARM_COLORS["reduced8"], label="8 ranked sensors")
        ax.set_xticks(xs)
        ax.set_xlabel(title + (" (recipe 30)" if "window" in title else " (recipe 125)"))
        ax.set_title(f"test RMSE vs {title}", fontsize=9)
    axes[0].set_ylabel("test RMSE (cycles)")
    axes[0].legend(fontsize=7)
    plotstyle.save(fig, FIG / "recipe_sensitivity")

    # 4. validation curves (the selection rule, visibly)
    sel = json.loads((ROOT / "results" / "selections.json").read_text())
    fig, ax = plt.subplots(figsize=(4.6, 2.8))
    for arm, s in sel.items():
        xs = sorted(int(k) for k in s["mean_val_rmse_by_n"])
        ys = [s["mean_val_rmse_by_n"][str(k)] for k in xs]
        ax.plot(xs, ys, marker="o", markersize=3, color=plotstyle.ARM_COLORS.get(arm, plotstyle.MUTED), label=ARM_LABEL.get(arm, arm))
        ax.plot([s["n_estimators"]], [s["mean_val_rmse_by_n"][str(s["n_estimators"])]], marker="o", markersize=10, markerfacecolor="none",
                color=plotstyle.ARM_COLORS.get(arm, plotstyle.MUTED))
    ax.set_xlabel("number of trees")
    ax.set_ylabel("validation RMSE (mean of 3 seeds)")
    ax.set_title("Model selection on the validation engines only", fontsize=9)
    ax.legend(fontsize=7)
    plotstyle.save(fig, FIG / "validation_curves")

    # 5. sensor importance of the deployed model, coloured by membership of the 8 ranked sensors
    audit = json.loads((ROOT / "results" / "audit_main.json").read_text())
    arms = json.loads((ROOT / "data" / "splits" / "arms.json").read_text())
    imp = {k: v for k, v in audit["full21_importance_by_sensor"].items() if v > 0}
    ks = list(imp)
    fig, ax = plt.subplots(figsize=(5.6, 2.6))
    ax.bar(range(len(ks)), [imp[k] for k in ks], color=[plotstyle.ARM_COLORS["reduced8"] if k in arms["reduced8"] else plotstyle.SERIES[0] for k in ks], width=0.7)
    ax.set_xticks(range(len(ks)), [k[1:] for k in ks], fontsize=8)
    ax.set_xlabel("sensor (orange: in the 8 ranked sensors)")
    ax.set_ylabel("share of importance")
    ax.set_title("Where the 21-sensor model puts its weight", fontsize=9)
    plotstyle.save(fig, FIG / "sensor_importance")

    # 6. alert timeline for one test engine, from the service's own replay
    rep = json.loads((ROOT / "results" / "alert_replay_test.json").read_text())
    from error_analysis import frame
    df = frame()
    eng = sorted(rep["engines"], key=lambda e: e["life"])[len(rep["engines"]) // 2]
    e = df[df.unit == eng["unit"]]
    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    ax.axhspan(0, 30, color=plotstyle.STATUS["CRITICAL"], alpha=0.08, linewidth=0)
    ax.axhspan(30, 60, color=plotstyle.STATUS["WARNING"], alpha=0.12, linewidth=0)
    ax.plot(e.cycle, e.true, color=plotstyle.INK_2, linewidth=1.3, label="true remaining life (capped)")
    ax.plot(e.cycle, e.pred, color=plotstyle.SERIES[0], linewidth=1.1, label="predicted by the service's model")
    for al in eng["alerts"]:
        c = plotstyle.STATUS[al["severity"]]
        ax.axvline(al["opened_cycle"], color=c, linewidth=1.5)
        ax.text(al["opened_cycle"] + 2, 112, f"{al['severity']} opens\n{al['true_rul_at_open']} cycles before failure", fontsize=7, color=plotstyle.INK)
    ax.set_xlabel("cycle")
    ax.set_ylabel("remaining useful life (cycles)")
    ax.set_title(f"Test engine {eng['unit']} replayed to failure: one WARNING, then one CRITICAL", fontsize=9)
    ax.legend(loc="lower left", fontsize=7)
    plotstyle.save(fig, FIG / "alert_timeline")

    # 7. load test before / after
    if lt is not None and len(lt):
        fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.6))
        xs = np.arange(len(lt))
        axes[0].bar(xs, lt.readings_per_s, color=plotstyle.SERIES[0], width=0.6)
        for xi, v in zip(xs, lt.readings_per_s):
            axes[0].text(xi, v, fmt(v, 0), ha="center", va="bottom", fontsize=7.5, color=plotstyle.INK_2)
        axes[0].set_title("throughput (readings per second)", fontsize=9)
        w = 0.26
        for j, (col, lab) in enumerate([("p50_ms", "p50"), ("p95_ms", "p95"), ("p99_ms", "p99")]):
            axes[1].bar(xs + (j - 1) * w, lt[col], width=w, color=plotstyle.SEQUENTIAL[2 + 3 * j], label=lab)
        axes[1].set_title("request latency (ms)", fontsize=9)
        axes[1].legend(fontsize=7)
        for ax in axes:
            ax.set_xticks(xs, lt.label, fontsize=7, rotation=15)
        plotstyle.save(fig, FIG / "loadtest")


# ---------------------------------------------------------------- numbers
def numbers(summary, runs, lt) -> dict:
    n: dict[str, str] = {}

    def put(key, value, nd=2):
        if isinstance(value, (bool, np.bool_)):
            n[key] = "yes" if value else "no"
        elif isinstance(value, (int, np.integer)):
            n[key] = str(int(value))
        elif isinstance(value, (float, np.floating)):
            n[key] = fmt(float(value), nd)
        else:
            n[key] = str(value)

    for _, r in summary.iterrows():
        k = f"{r.phase}_{r.model}_{r.arm}"
        put(f"{k}_test_rmse", r.test_rmse_mean)
        put(f"{k}_test_rmse_std", r.test_rmse_std)
        put(f"{k}_test_mae", r.test_mae_mean)
        put(f"{k}_test_nasa", r.test_nasa_mean)
        put(f"{k}_status_acc", r.status_acc_mean, 3)
        put(f"{k}_status_acc_pct", 100 * r.status_acc_mean, 1)
        put(f"{k}_status_f1", r.status_f1_mean, 3)
        put(f"{k}_critical_recall", r.critical_recall_mean, 3)
        put(f"{k}_official_rmse", r.official_rmse_mean)
        put(f"{k}_n_estimators", int(r.n_estimators))
        put(f"{k}_n_sensors", int(r.n_sensors))
        put(f"{k}_train_seconds", r.train_seconds_mean, 0)

    full, red = row(summary, "main", "full21"), row(summary, "main", "reduced8")
    paired = (runs[(runs.phase == "main") & (runs.arm == "reduced8")].sort_values("seed").test_rmse.to_numpy()
              - runs[(runs.phase == "main") & (runs.arm == "full21")].sort_values("seed").test_rmse.to_numpy())
    put("margin", MARGIN, 1)
    put("hyp_gap", red.test_rmse_mean - full.test_rmse_mean)
    put("hyp_gap_min", paired.min())
    put("hyp_gap_max", paired.max())
    put("hyp_holds", bool(red.test_rmse_mean - full.test_rmse_mean < MARGIN))
    put("deployed_arm", "full21" if red.test_rmse_mean - full.test_rmse_mean >= MARGIN else "reduced8")
    put("triv_over_gbr", row(summary, "baseline", "full21", "trivial_mean").test_rmse_mean / full.test_rmse_mean, 1)

    for name in ("greedy8", "worst8"):
        r = row(summary, "posthoc", name)
        if r is not None:
            put(f"{name}_gap", r.test_rmse_mean - full.test_rmse_mean)
    rnd = runs[runs.arm.str.startswith("random8-")]
    if len(rnd):
        put("random8_test_rmse", rnd.test_rmse.mean())
        put("random8_test_rmse_std", rnd.test_rmse.std())
        put("random8_gap", rnd.test_rmse.mean() - full.test_rmse_mean)
        put("random8_draws", rnd.arm.nunique())
    for tag, a21, a8 in [("w10", "full21-w10", "reduced8-w10"), ("w60", "full21-w60", "reduced8-w60"),
                         ("cap100", "full21-cap100", "reduced8-cap100"), ("cap150", "full21-cap150", "reduced8-cap150")]:
        r21, r8 = row(summary, "posthoc", a21), row(summary, "posthoc", a8)
        if r21 is not None and r8 is not None:
            put(f"gap_{tag}", r8.test_rmse_mean - r21.test_rmse_mean)
    w60 = row(summary, "posthoc", "full21-w60")
    if w60 is not None:
        put("window_effect_full21", full.test_rmse_mean - w60.test_rmse_mean)
    rs = row(summary, "posthoc", "full21-rowsplit")
    if rs is not None:
        put("rowsplit_rmse", rs.test_rmse_mean)
        put("rowsplit_optimism", full.test_rmse_mean - rs.test_rmse_mean)
        put("rowsplit_optimism_pct", 100 * (full.test_rmse_mean - rs.test_rmse_mean) / full.test_rmse_mean, 0)

    g8 = json.loads((ROOT / "results" / "greedy8.json").read_text())
    arms = json.loads((ROOT / "data" / "splits" / "arms.json").read_text())
    put("greedy8_sensors", ", ".join(s[1:] for s in sorted(g8["selected"], key=lambda s: int(s[1:]))))
    put("reduced8_sensors", ", ".join(s[1:] for s in arms["reduced8"]))
    put("informative_sensors", ", ".join(s[1:] for s in arms["informative15"]))
    put("constant_sensors", ", ".join(s[1:] for s in arms["full21"] if s not in arms["informative15"]))
    red = json.loads((ROOT / "results" / "redundancy.json").read_text())
    for k in ("reduced8", "worst8", "greedy8", "informative15"):
        put(f"redundancy_{k}", red[k], 2)
    ca = json.loads((ROOT / "results" / "config_audit.json").read_text())
    put("config_audit_verdict", ca["verdict"])
    put("config_audit_changed", ", ".join(ca["changed_fields"]))
    put("config_audit_affecting", len(ca["fields_affecting_training_or_evaluation"]))
    hashes = runs[runs.phase == "main"].groupby("config_hash").arm.apply(lambda s: ", ".join(sorted(set(s))))
    put("main_config_hashes", "; ".join(f"{h} ({a})" for h, a in hashes.items()))
    put("n_main_config_hashes", len(hashes))
    if len(rnd):
        best_rnd = rnd.groupby("arm").test_rmse.mean()
        put("random8_best_gap", best_rnd.min() - full.test_rmse_mean)
        put("random8_worst_gap", best_rnd.max() - full.test_rmse_mean)
    # configuration constants, read from the files that define them (so prose never types them either)
    split = json.loads((ROOT / "data" / "splits" / "fd001_split.json").read_text())
    for k in ("train", "val", "test"):
        put(f"split_{k}", len(split[k]))
    model_cfg = CONFIG["model"]
    put("cfg_learning_rate", model_cfg["learning_rate"], 2)
    put("cfg_max_depth", model_cfg["max_depth"])
    put("cfg_subsample", model_cfg["subsample"], 1)
    from train import GRID
    put("cfg_grid_min", GRID[0])
    put("cfg_grid_max", model_cfg["max_estimators"])
    put("cfg_features_full", 3 * len(arms["full21"]))
    put("cfg_parity_tol_exp", int(round(np.log10(CONFIG["parity_tolerance"]["onnx_prediction_abs"]))))
    put("cfg_feature_tol_exp", int(round(np.log10(CONFIG["parity_tolerance"]["features_java_vs_python_abs"]))))
    from alert_sim import SERVICE_RULES, service_rules
    service_rules()  # asserts the documented rules are the ones in application.yml
    for k, v in SERVICE_RULES.items():
        put("alert_" + k.replace("-", "_"), v, 1 if isinstance(v, float) else 0)
    fx = json.loads((ROOT / "tests" / "fixtures" / f"parity_{json.loads((ROOT / 'service' / 'src' / 'main' / 'resources' / 'models' / 'rul.json').read_text())['arm']}.json").read_text())
    put("parity_rows", len(fx["rows"]))
    from alert_sim import Rules
    put("original_trend_drop", Rules().trend_drop, 0)  # the pre-chosen rule, kept as the simulator's default
    put("original_trend_window", Rules().trend_window)
    put("n_runs_total", len(runs))
    put("n_runs_main", int((runs.phase == "main").sum()))
    put("n_runs_posthoc", int((runs.phase == "posthoc").sum()))
    put("config_hash", runs[runs.phase == "main"].config_hash.iloc[0])
    put("window", CONFIG["window"]["size"])
    put("label_cap", CONFIG["label"]["cap"])
    put("n_seeds", len(CONFIG["seeds"]))

    eda = json.loads((ROOT / "results" / "eda_summary.json").read_text())
    for k in ("rows", "engines", "life_min", "life_max"):
        put(f"eda_{k}", eda[k])
    put("eda_life_median", int(eda["life_median"]))
    put("eda_share_rows_above_cap", 100 * eda["share_rows_above_cap"], 1)

    audit = json.loads((ROOT / "results" / "audit_main.json").read_text())
    put("audit_const_splits", audit["full21_vs_informative15"]["splits_on_constant_sensor_features"])
    put("audit_importance_outside_pct", 100 * audit["importance_share_outside_reduced8"], 1)
    put("audit_top_outside", ", ".join(s[1:] for s in audit["top_sensors_outside_reduced8"]))

    for name in ("alert_replay_val", "alert_replay_test"):
        s = json.loads((ROOT / "results" / f"{name}.json").read_text())["summary"]
        for k in ("engines", "engines_passing", "alerts_total", "mean_true_rul_at_warning", "min_true_rul_at_warning",
                  "mean_true_rul_at_critical", "min_true_rul_at_critical"):
            put(f"{name}_{k}", s[k], 1)
    design = json.loads((ROOT / "results" / "alert_rule_design_val.json").read_text())
    put("alert_original_pass", design["candidates"]["original: drop>20 over 10"]["passing"])
    put("alert_original_alerts", design["candidates"]["original: drop>20 over 10"]["alerts"])
    put("alert_chosen_pass", design["candidates"][design["chosen"]]["passing"])

    rt = json.loads((ROOT / "results" / "restart_test.json").read_text())
    for k in ("file_rows", "readings_rows", "health_scores_rows", "machines_scored_exactly_1_to_life", "machines",
              "redelivered_and_ignored_as_late", "final_consumer_lag", "machines_with_alerts_different_from_uninterrupted_run",
              "machines_with_repeated_alert_of_one_severity"):
        put(f"restart_{k}", rt[k])
    put("restart_max_diff", f"{rt['max_abs_diff_vs_reference']:.0e}".replace("-", "−"))
    put("restart_seconds_down", rt["timeline"][2]["seconds_down"], 1)
    put("restart_peak_lag", rt["timeline"][1]["lag"])
    put("restart_readings_while_down", rt["timeline"][1]["readings"] - rt["timeline"][0]["readings_so_far"])
    put("restart_passed", rt["passed"])
    put("all_engines_alert_pass", rt["machines"] - rt["machines_with_repeated_alert_of_one_severity"])

    ea = json.loads((ROOT / "results" / "error_analysis.json").read_text())
    for k in ("test_rows", "misclassified_rows", "inspected", "ambiguous", "mislabeled", "model", "top_confusion_rows",
              "second_confusion_rows", "healthy_as_critical_rows", "critical_as_healthy_rows"):
        put(f"ea_{k}", ea[k])
    put("ea_misclassified_pct", 100 * ea["misclassified_share"], 1)
    put("ea_small_error_pct", 100 * ea["population_small_error_share"], 0)
    for k, v in ea["patterns"].items():
        put(f"ea_pattern_{k}", v)

    if lt is not None and len(lt):
        for _, r in lt.iterrows():
            k = re.sub(r"[^A-Za-z0-9]+", "_", r.label)
            put(f"lt_{k}_rps", r.readings_per_s, 0)
            put(f"lt_{k}_p50", r.p50_ms, 1)
            put(f"lt_{k}_p95", r.p95_ms, 1)
            put(f"lt_{k}_p99", r.p99_ms, 1)
            put(f"lt_{k}_vus", int(r.vus))
            put(f"lt_{k}_batch", int(r.batch))
            put(f"lt_{k}_pool_pending", r.pool_pending_mean, 1)
        best = lt.loc[lt.readings_per_s.idxmax()]
        put("lt_best_label", best.label)
        put("lt_best_rps", best.readings_per_s, 0)
        put("lt_best_p95", best.p95_ms, 1)
        put("lt_best_p99", best.p99_ms, 1)

    infer = json.loads((ROOT / "results" / "java_inference.json").read_text()) if (ROOT / "results" / "java_inference.json").exists() else {}
    for k, v in infer.items():
        put(f"java_{k}", v, 1)
    cov = ROOT / "results" / "coverage.json"
    if cov.exists():
        for k, v in json.loads(cov.read_text()).items():
            put(f"coverage_{k}", v, 1)
    tests = ROOT / "results" / "test_counts.json"
    if tests.exists():
        for k, v in json.loads(tests.read_text()).items():
            put(f"tests_{k}", v)
    return n


def write_macros(n: dict) -> None:
    lines = ["% Generated by model/report.py from the results files. Do not edit by hand."]
    seen = {}
    for k, v in n.items():
        name = macro_name(k)
        assert name not in seen, f"macro collision: {k} and {seen[name]} -> {name}"
        seen[name] = k
        val = tex_escape(v).replace("−", "$-$").replace("±", "$\\pm$")
        lines.append(f"\\newcommand{{\\{name}}}{{{val}}}")
    NUMBERS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    NUMBERS_JSON.write_text(json.dumps(n, indent=2, ensure_ascii=False), encoding="utf-8")


def render(template: Path, out: Path, n: dict, t: dict) -> None:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(loader=FileSystemLoader(str(template.parent)), undefined=StrictUndefined, keep_trailing_newline=True)
    out.write_text(env.get_template(template.name).render(n=n, t=t), encoding="utf-8")


def main() -> None:
    runs = load_runs()
    summary = summarise(runs)
    TABLES.mkdir(parents=True, exist_ok=True)
    t = {}
    for name, (md, tex) in {"main": main_table(summary), "which8": which8_table(summary, runs), "recipe": recipe_table(summary)}.items():
        (TABLES / f"{name}.md").write_text(md, encoding="utf-8")
        (TABLES / f"{name}.tex").write_text(tex, encoding="utf-8")
        t[name] = md
    md_lt, tex_lt, lt = loadtest_table()
    (TABLES / "loadtest.md").write_text(md_lt, encoding="utf-8")
    (TABLES / "loadtest.tex").write_text(tex_lt, encoding="utf-8")
    t["loadtest"] = md_lt
    summary.to_csv(TABLES / "summary.csv", index=False)
    figures(summary, runs, lt)
    n = numbers(summary, runs, lt)
    write_macros(n)
    for tpl, out in [(REPORT / "README.template.md", ROOT / "README.md"), (REPORT / "RESULTS.template.md", ROOT / "showcase" / "RESULTS.md"),
                     (REPORT / "posts.template.md", ROOT / "showcase" / "posts.md")]:
        if tpl.exists():
            out.parent.mkdir(exist_ok=True)
            render(tpl, out, n, t)
    print(t["main"], "\n\n", t["which8"], "\n\n", t["recipe"])
    print(f"\n{len(n)} numbers -> {NUMBERS.name}, {NUMBERS_JSON.name}")


if __name__ == "__main__":
    main()

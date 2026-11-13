"""Everything derived from results/runs.csv: tables (Markdown + LaTeX), figures, report/numbers.tex macros,
and the README rendered from report/README.template.md. No number in any document is typed by hand.

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
MACROS_JSON = ROOT / "results" / "numbers.json"

ARM_LABEL = {"full21": "all 21 sensors", "informative15": "15 informative sensors", "reduced8": "8 ranked sensors"}
MODEL_LABEL = {"trivial_mean": "trivial (train mean)", "ridge": "ridge regression", "gbr": "gradient boosting"}

# LaTeX macro names cannot contain digits; spell them out.
DIGITS = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four", "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}


def macro_name(key: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", key)
    out = ""
    for p in parts:
        for ch in p:
            out += DIGITS[ch] if ch.isdigit() else ch
        out = out[:1].upper() + out[1:] if out else out
    # camel-case each part
    words = re.split(r"[^A-Za-z]+", key)
    name = "".join(w[:1].upper() + w[1:] for w in words if w)
    for d, w in DIGITS.items():
        name = name.replace(d, w)
    return name


def fmt(x, nd=2) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "--"
    s = f"{x:.{nd}f}"
    return s.replace("-", "−")  # proper minus sign


def summarise(runs: pd.DataFrame) -> pd.DataFrame:
    """Mean and std over seeds per (phase, arm, model)."""
    g = runs.groupby(["phase", "arm", "model"], sort=False)
    agg = g.agg(
        n_runs=("run_id", "count"),
        n_sensors=("n_sensors", "first"),
        n_estimators=("n_estimators", "first"),
        window=("window", "first"),
        cap=("cap", "first"),
        val_rmse_mean=("val_rmse", "mean"),
        test_rmse_mean=("test_rmse", "mean"), test_rmse_std=("test_rmse", "std"),
        test_mae_mean=("test_mae", "mean"), test_mae_std=("test_mae", "std"),
        test_nasa_mean=("test_nasa", "mean"), test_nasa_std=("test_nasa", "std"),
        status_acc_mean=("test_status_acc", "mean"), status_f1_mean=("test_status_f1_macro", "mean"),
        critical_recall_mean=("test_critical_recall", "mean"),
        official_rmse_mean=("official_rmse", "mean"), official_rmse_std=("official_rmse", "std"),
        official_nasa_mean=("official_nasa", "mean"),
        train_seconds_mean=("train_seconds", "mean"),
    ).reset_index()
    return agg.fillna({"test_rmse_std": 0, "test_mae_std": 0, "test_nasa_std": 0, "official_rmse_std": 0})


def pm(m, s, nd=2) -> str:
    return f"{fmt(m, nd)} ± {fmt(s, nd)}"


def main_table(summary: pd.DataFrame) -> tuple[str, str]:
    rows = []
    order = [("baseline", "trivial_mean", "full21"), ("baseline", "ridge", "full21"), ("baseline", "ridge", "reduced8"),
             ("main", "gbr", "full21"), ("main", "gbr", "informative15"), ("main", "gbr", "reduced8")]
    for phase, model, arm in order:
        r = summary[(summary.phase == phase) & (summary.model == model) & (summary.arm == arm)]
        if r.empty:
            continue
        r = r.iloc[0]
        rows.append({
            "Method": f"{MODEL_LABEL[model]}, {ARM_LABEL[arm]}",
            "Sensors": int(r.n_sensors),
            "Seeds": int(r.n_runs),
            "Test RMSE": pm(r.test_rmse_mean, r.test_rmse_std),
            "Test MAE": pm(r.test_mae_mean, r.test_mae_std),
            "NASA score": pm(r.test_nasa_mean, r.test_nasa_std),
            "Status acc.": fmt(r.status_acc_mean, 3),
            "Macro-F1": fmt(r.status_f1_mean, 3),
            "Official RMSE": pm(r.official_rmse_mean, r.official_rmse_std),
        })
    df = pd.DataFrame(rows)
    md = df.to_markdown(index=False)
    tex = df.to_latex(index=False, escape=False, column_format="l" + "r" * (len(df.columns) - 1)).replace("±", "$\\pm$")
    return md, tex


def ablation_table(summary: pd.DataFrame) -> tuple[str, str]:
    post = summary[summary.phase == "posthoc"].copy()
    if post.empty:
        return "(no ablations yet)", "% no ablations yet"
    main = summary[summary.phase == "main"].set_index("arm")
    rows = []
    for _, r in post.iterrows():
        base_arm = "reduced8" if r.arm.startswith("reduced8") or r.arm.startswith("random8") or r.arm == "worst8" else "full21"
        base = main.loc[base_arm].test_rmse_mean if base_arm in main.index else np.nan
        rows.append({"Setting": r.arm, "Window": int(r.window), "Cap": int(r.cap), "Trees": int(r.n_estimators),
                     "Test RMSE": pm(r.test_rmse_mean, r.test_rmse_std),
                     "vs. recipe": fmt(r.test_rmse_mean - base)})
    df = pd.DataFrame(rows)
    return df.to_markdown(index=False), df.to_latex(index=False, escape=False, column_format="lrrrrr").replace("±", "$\\pm$")


def hypothesis(summary: pd.DataFrame, runs: pd.DataFrame) -> dict:
    main = summary[summary.phase == "main"].set_index("arm")
    out = {"margin": 1.0}
    if {"full21", "reduced8"} <= set(main.index):
        gap = float(main.loc["reduced8"].test_rmse_mean - main.loc["full21"].test_rmse_mean)
        f = runs[(runs.phase == "main") & (runs.arm == "full21")].test_rmse.to_numpy()
        r = runs[(runs.phase == "main") & (runs.arm == "reduced8")].test_rmse.to_numpy()
        gaps = r - f  # same seeds, paired
        out.update({"gap": gap, "gap_std": float(np.std(gaps, ddof=1)) if len(gaps) > 1 else 0.0,
                    "gap_min": float(gaps.min()), "gap_max": float(gaps.max()),
                    "holds": bool(gap < 1.0), "deployed_arm": "reduced8" if gap < 1.0 else "full21"})
    return out


def figures(summary: pd.DataFrame, runs: pd.DataFrame) -> None:
    plotstyle.apply()
    import matplotlib.pyplot as plt

    # Main figure: test RMSE per method, mean +- std over seeds, trivial baseline as a reference line
    order = [("baseline", "ridge", "full21"), ("baseline", "ridge", "reduced8"),
             ("main", "gbr", "full21"), ("main", "gbr", "informative15"), ("main", "gbr", "reduced8")]
    labels, means, stds, colors = [], [], [], []
    for phase, model, arm in order:
        r = summary[(summary.phase == phase) & (summary.model == model) & (summary.arm == arm)]
        if r.empty:
            continue
        r = r.iloc[0]
        labels.append(f"{MODEL_LABEL[model]}\n{ARM_LABEL[arm]}")
        means.append(r.test_rmse_mean)
        stds.append(r.test_rmse_std)
        colors.append(plotstyle.ARM_COLORS[arm])
    triv = summary[(summary.model == "trivial_mean")]
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    x = np.arange(len(labels))
    ax.bar(x, means, color=colors, width=0.62, yerr=stds, capsize=3, error_kw={"elinewidth": 1, "ecolor": plotstyle.INK_2})
    for xi, m in zip(x, means):
        ax.text(xi, m + 0.6, fmt(m), ha="center", va="bottom", color=plotstyle.INK_2, fontsize=8)
    if not triv.empty:
        ax.axhline(triv.iloc[0].test_rmse_mean, color=plotstyle.MUTED, linestyle="--", linewidth=1)
        ax.text(len(labels) - 0.5, triv.iloc[0].test_rmse_mean + 0.6, f"trivial baseline {fmt(triv.iloc[0].test_rmse_mean, 1)}",
                ha="right", color=plotstyle.MUTED, fontsize=8)
    ax.set_xticks(x, labels, fontsize=7.5)
    ax.set_ylabel("test RMSE (cycles), lower is better")
    ax.set_title("RUL error on 15 held-out engines (mean ± std over 3 seeds)")
    ax.set_ylim(0, max(means + [triv.iloc[0].test_rmse_mean if not triv.empty else 0]) * 1.15)
    plotstyle.save(fig, FIG / "main_test_rmse")

    # Validation curves: mean val RMSE by n_estimators per arm (the selection rule, visibly)
    sel_path = ROOT / "results" / "selections.json"
    if sel_path.exists():
        sel = json.loads(sel_path.read_text())
        fig, ax = plt.subplots(figsize=(4.6, 2.8))
        for arm, s in sel.items():
            xs = sorted(int(k) for k in s["mean_val_rmse_by_n"])
            ys = [s["mean_val_rmse_by_n"][str(k)] for k in xs]
            ax.plot(xs, ys, marker="o", color=plotstyle.ARM_COLORS.get(arm, plotstyle.MUTED), label=ARM_LABEL.get(arm, arm))
            ax.plot([s["n_estimators"]], [s["mean_val_rmse_by_n"][str(s["n_estimators"])]], marker="o", markersize=10,
                    markerfacecolor="none", color=plotstyle.ARM_COLORS.get(arm, plotstyle.MUTED))
        ax.set_xlabel("number of trees")
        ax.set_ylabel("validation RMSE (mean of 3 seeds)")
        ax.set_title("Model selection on the validation engines only")
        ax.legend()
        plotstyle.save(fig, FIG / "validation_curves")

    # Seeds scatter: every main run, paired by seed
    main = runs[runs.phase == "main"]
    if not main.empty:
        fig, ax = plt.subplots(figsize=(4.6, 2.8))
        arms = [a for a in ("full21", "informative15", "reduced8") if a in set(main.arm)]
        for i, arm in enumerate(arms):
            sub = main[main.arm == arm].sort_values("seed")
            ax.scatter(np.full(len(sub), i) + (sub.seed - 1) * 0.08, sub.test_rmse, color=plotstyle.ARM_COLORS[arm], s=36, zorder=3)
            for _, r in sub.iterrows():
                ax.text(i + (r.seed - 1) * 0.08, r.test_rmse + 0.08, f"s{int(r.seed)}", ha="center", fontsize=6.5, color=plotstyle.INK_2)
        ax.set_xticks(range(len(arms)), [ARM_LABEL[a] for a in arms], fontsize=8)
        ax.set_ylabel("test RMSE (cycles)")
        ax.set_title("Every run, by seed")
        plotstyle.save(fig, FIG / "seeds_scatter")


def write_macros(summary: pd.DataFrame, runs: pd.DataFrame, hyp: dict, extra: dict) -> dict:
    macros: dict[str, str] = {}

    def put(key, value, nd=2):
        macros[key] = fmt(value, nd) if isinstance(value, (int, float, np.floating, np.integer)) and not isinstance(value, bool) else str(value)

    for _, r in summary.iterrows():
        k = f"{r.phase}_{r.model}_{r.arm}"
        put(f"{k}_test_rmse", r.test_rmse_mean)
        put(f"{k}_test_rmse_std", r.test_rmse_std)
        put(f"{k}_test_mae", r.test_mae_mean)
        put(f"{k}_test_nasa", r.test_nasa_mean)
        put(f"{k}_status_acc", r.status_acc_mean, 3)
        put(f"{k}_status_f1", r.status_f1_mean, 3)
        put(f"{k}_critical_recall", r.critical_recall_mean, 3)
        put(f"{k}_official_rmse", r.official_rmse_mean)
        put(f"{k}_official_rmse_std", r.official_rmse_std)
        put(f"{k}_official_nasa", r.official_nasa_mean)
        put(f"{k}_n_estimators", int(r.n_estimators), 0)
        put(f"{k}_n_sensors", int(r.n_sensors), 0)
        put(f"{k}_train_seconds", r.train_seconds_mean, 0)
    for key, v in hyp.items():
        put(f"hyp_{key}", v)
    for key, v in extra.items():
        put(key, v, extra.get("_nd", {}).get(key, 2) if isinstance(extra.get("_nd"), dict) else 2)
    macros.pop("_nd", None)
    put("n_runs_total", len(runs), 0)
    put("n_runs_main", int((runs.phase == "main").sum()), 0)
    put("n_runs_posthoc", int((runs.phase == "posthoc").sum()), 0)
    put("config_hash", runs.config_hash.iloc[-1] if len(runs) else "")
    put("window", CONFIG["window"]["size"], 0)
    put("cap", CONFIG["label"]["cap"], 0)
    put("n_seeds", len(CONFIG["seeds"]), 0)
    arms = json.loads((ROOT / "data" / "splits" / "arms.json").read_text())
    put("reduced8_sensors", ", ".join(s[1:] for s in arms["reduced8"]))
    put("informative_sensors", ", ".join(s[1:] for s in arms["informative15"]))
    eda = json.loads((ROOT / "results" / "eda_summary.json").read_text())
    for key in ("rows", "engines", "life_min", "life_max"):
        put(f"eda_{key}", eda[key], 0)
    put("eda_life_median", eda["life_median"], 0)
    put("eda_share_rows_above_cap", 100 * eda["share_rows_above_cap"], 1)

    lines = ["% Generated by model/report.py from results/runs.csv. Do not edit by hand."]
    for k, v in macros.items():
        name = macro_name(k)
        lines.append(f"\\newcommand{{\\{name}}}{{{v}}}")
    NUMBERS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    MACROS_JSON.write_text(json.dumps(macros, indent=2), encoding="utf-8")
    return macros


def render_readme(macros: dict, tables: dict) -> None:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(loader=FileSystemLoader(str(REPORT)), undefined=StrictUndefined, keep_trailing_newline=True)
    tpl = env.get_template("README.template.md")
    text = tpl.render(n=macros, t=tables)
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    runs = load_runs()
    summary = summarise(runs)
    TABLES.mkdir(parents=True, exist_ok=True)
    md_main, tex_main = main_table(summary)
    md_abl, tex_abl = ablation_table(summary)
    (TABLES / "main.md").write_text(md_main, encoding="utf-8")
    (TABLES / "main.tex").write_text(tex_main, encoding="utf-8")
    (TABLES / "ablations.md").write_text(md_abl, encoding="utf-8")
    (TABLES / "ablations.tex").write_text(tex_abl, encoding="utf-8")
    summary.to_csv(TABLES / "summary.csv", index=False)
    hyp = hypothesis(summary, runs)
    figures(summary, runs)
    extra = {}
    for name in ("loadtest_summary.json", "restart_test.json", "error_analysis.json", "alert_replay.json"):
        p = ROOT / "results" / name
        if p.exists():
            extra.update({f"{name.split('.')[0]}_{k}": v for k, v in json.loads(p.read_text()).items() if isinstance(v, (int, float, str))})
    macros = write_macros(summary, runs, hyp, extra)
    tables = {"main": md_main, "ablations": md_abl}
    if (REPORT / "README.template.md").exists():
        render_readme(macros, tables)
    print(json.dumps(hyp, indent=2))
    print(md_main)


if __name__ == "__main__":
    main()

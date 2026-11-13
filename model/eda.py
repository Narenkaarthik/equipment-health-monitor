"""Block 0: exploratory data analysis of NASA C-MAPSS FD001.

Writes figures to report/figures/ and a machine-readable summary to results/eda_summary.json.
Nothing here feeds model selection; it only documents what the raw data looks like.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
import plotstyle  # noqa: E402
from data import COLUMNS, SENSORS, load_train  # noqa: E402

FIG = ROOT / "report" / "figures"


def main() -> None:
    plotstyle.apply()
    import matplotlib.pyplot as plt

    df = load_train()
    lengths = df.groupby("unit").cycle.max()
    std = df[SENSORS].std()
    constant = sorted(std[std < 1e-6].index, key=lambda s: int(s[1:]))
    df["rul"] = df.groupby("unit").cycle.transform("max") - df.cycle
    rho = df[SENSORS + ["rul"]].corr(method="spearman")["rul"].drop("rul")

    # --- Figure: engine life lengths
    fig, ax = plt.subplots(figsize=(4.2, 2.6))
    ax.hist(lengths, bins=24, color=plotstyle.SERIES[0], edgecolor=plotstyle.SURFACE, linewidth=0.8)
    ax.axvline(lengths.median(), color=plotstyle.INK_2, linewidth=1, linestyle="--")
    ax.text(lengths.median() + 3, ax.get_ylim()[1] * 0.92, f"median {int(lengths.median())}", color=plotstyle.INK_2)
    ax.set_xlabel("cycles to failure")
    ax.set_ylabel("engines")
    ax.set_title("FD001: run-to-failure length of the 100 training engines")
    plotstyle.save(fig, FIG / "eda_engine_lengths")

    # --- Figure: four sensors for one engine, raw vs rolling mean
    unit = 1
    one = df[df.unit == unit]
    picks = ["s2", "s4", "s11", "s7"]
    fig, axes = plt.subplots(2, 2, figsize=(6.4, 3.8), sharex=True)
    for ax, s in zip(axes.ravel(), picks):
        ax.plot(one.cycle, one[s], color=plotstyle.SEQUENTIAL[1], linewidth=0.8, label="raw")
        ax.plot(one.cycle, one[s].rolling(30).mean(), color=plotstyle.SEQUENTIAL[6], linewidth=1.6, label="30-cycle mean")
        ax.set_title(f"sensor {s[1:]}")
        ax.grid(True, axis="y")
    axes[1, 0].set_xlabel("cycle")
    axes[1, 1].set_xlabel("cycle")
    axes[0, 0].legend(loc="upper left")
    fig.suptitle(f"Engine {unit}: noisy sensors drift as the engine degrades", y=1.02)
    plotstyle.save(fig, FIG / "eda_sensor_traces")

    # --- Figure: |Spearman rho| with RUL per sensor (constant sensors shown as zero)
    order = sorted(SENSORS, key=lambda s: int(s[1:]))
    vals = [0.0 if np.isnan(rho[s]) else abs(rho[s]) for s in order]
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    colors = [plotstyle.MUTED if s in constant else plotstyle.SERIES[0] for s in order]
    ax.bar([s[1:] for s in order], vals, color=colors, width=0.7)
    ax.set_ylabel("|Spearman rho| with RUL")
    ax.set_xlabel("sensor")
    ax.set_title("Which sensors track remaining life (grey = constant in FD001)")
    plotstyle.save(fig, FIG / "eda_sensor_correlation")

    # --- Figure: RUL distribution raw vs capped at 125
    fig, ax = plt.subplots(figsize=(4.2, 2.6))
    ax.hist(df.rul, bins=50, color=plotstyle.SEQUENTIAL[1], label="true RUL")
    ax.hist(df.rul.clip(upper=125), bins=50, color=plotstyle.SEQUENTIAL[6], alpha=0.85, label="capped at 125")
    ax.set_xlabel("remaining useful life (cycles)")
    ax.set_ylabel("rows")
    ax.legend()
    ax.set_title("RUL label: raw and capped")
    plotstyle.save(fig, FIG / "eda_rul_distribution")

    summary = {
        "rows": int(len(df)),
        "engines": int(df.unit.nunique()),
        "columns": int(len(COLUMNS)),
        "cycles_contiguous_from_one": bool((df.groupby("unit").cycle.agg(["min", "max", "count"]).eval("min == 1 and max == count")).all()),
        "duplicate_unit_cycle_rows": int(df.duplicated(["unit", "cycle"]).sum()),
        "missing_values": int(df[COLUMNS].isna().sum().sum()),
        "life_min": int(lengths.min()),
        "life_median": float(lengths.median()),
        "life_max": int(lengths.max()),
        "constant_sensors": constant,
        "informative_sensors": [s for s in order if s not in constant],
        "spearman_abs_rho": {s: (None if np.isnan(rho[s]) else round(float(abs(rho[s])), 4)) for s in order},
        "rows_with_rul_above_cap": int((df.rul > 125).sum()),
        "share_rows_above_cap": round(float((df.rul > 125).mean()), 4),
    }
    out = ROOT / "results" / "eda_summary.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

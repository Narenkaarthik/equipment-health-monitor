"""Sliding-window features: per sensor mean, standard deviation (ddof=0) and OLS slope over the last W
readings of a machine. The Java processor computes the same numbers incrementally in O(1) per reading;
the two implementations are compared on a fixture (tests/fixtures) in the Java unit tests.

Processed arrays are stored memory-mapped under data/processed/ (gitignored).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
CONFIG = json.loads((ROOT / "model" / "config" / "experiment.json").read_text())
WINDOW = int(CONFIG["window"]["size"])
STATS = ("mean", "std", "slope")


def window_features_1d(x: np.ndarray, w: int) -> np.ndarray:
    """Features for one sensor of one machine, rows in cycle order. Returns (len(x), 3): mean, std, slope.

    Row k uses the window x[max(0, k+1-w) : k+1] (so the first rows use fewer than w values).
    Each window is reduced directly (two-pass), which is exact to rounding; no running sums.
    """
    x = np.asarray(x, dtype=np.float64)
    L = len(x)
    if L == 0:
        return np.zeros((0, 3))
    padded = np.concatenate([np.full(w - 1, np.nan), x])
    win = sliding_window_view(padded, w)  # (L, w); NaN marks "before the first reading"
    valid = ~np.isnan(win)
    n = valid.sum(axis=1).astype(np.float64)
    mean = np.nansum(win, axis=1) / n
    dev = np.where(valid, win - mean[:, None], 0.0)
    std = np.sqrt((dev * dev).sum(axis=1) / n)
    # positions inside the window: the valid values occupy the last n columns -> i = col - (w - n)
    col = np.arange(w, dtype=np.float64)[None, :]
    pos = col - (w - n)[:, None]
    pos_mean = (n - 1) / 2.0
    pdev = np.where(valid, pos - pos_mean[:, None], 0.0)
    sxx = (pdev * pdev).sum(axis=1)
    sxy = (pdev * dev).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = np.where(n >= 2, sxy / sxx, 0.0)
    return np.column_stack([mean, std, slope])


def window_features_reference(x: np.ndarray, w: int) -> np.ndarray:
    """Slow, obviously-correct version used only by the tests."""
    out = np.zeros((len(x), 3))
    for k in range(len(x)):
        win = np.asarray(x[max(0, k + 1 - w) : k + 1], dtype=np.float64)
        n = len(win)
        out[k, 0] = win.mean()
        out[k, 1] = win.std(ddof=0)
        out[k, 2] = np.polyfit(np.arange(n), win, 1)[0] if n >= 2 else 0.0
    return out


def feature_names(sensors: list[str]) -> list[str]:
    return [f"{s}_{st}" for s in sensors for st in STATS]


def build_feature_frame(df: pd.DataFrame, sensors: list[str], w: int = WINDOW) -> pd.DataFrame:
    """Window features for every row of every machine. Keeps unit, cycle and (if present) rul."""
    df = df.sort_values(["unit", "cycle"]).reset_index(drop=True)
    cols = feature_names(sensors)
    blocks = []
    for _, g in df.groupby("unit", sort=False):
        feats = np.concatenate([window_features_1d(g[s].to_numpy(), w) for s in sensors], axis=1)
        blocks.append(feats)
    X = np.concatenate(blocks, axis=0)
    out = pd.DataFrame(X, columns=cols)
    out.insert(0, "cycle", df["cycle"].to_numpy())
    out.insert(0, "unit", df["unit"].to_numpy())
    if "rul" in df.columns:
        out["rul"] = df["rul"].to_numpy()
    return out


def save_memmap(name: str, arr: np.ndarray) -> Path:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    path = PROCESSED / f"{name}.npy"
    mm = np.lib.format.open_memmap(path, mode="w+", dtype=arr.dtype, shape=arr.shape)
    mm[:] = arr
    mm.flush()
    del mm
    return path


def load_memmap(name: str) -> np.ndarray:
    return np.load(PROCESSED / f"{name}.npy", mmap_mode="r")

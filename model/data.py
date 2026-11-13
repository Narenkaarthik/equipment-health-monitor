"""Loading C-MAPSS FD001 and the frozen, group-aware engine split.

Every engine is a group: all its cycles go to exactly one of train / val / test.
The split is frozen in data/splits/fd001_split.json and tests/test_split.py fails if a group leaks.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SPLIT_FILE = ROOT / "data" / "splits" / "fd001_split.json"

SETTINGS = ["os1", "os2", "os3"]
SENSORS = [f"s{i}" for i in range(1, 22)]
COLUMNS = ["unit", "cycle", *SETTINGS, *SENSORS]


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=r"\s+", header=None, names=COLUMNS, engine="python")
    df["unit"] = df["unit"].astype(int)
    df["cycle"] = df["cycle"].astype(int)
    return df


def load_train(subset: str = "FD001") -> pd.DataFrame:
    return _read(RAW / f"train_{subset}.txt")


def load_official_test(subset: str = "FD001") -> tuple[pd.DataFrame, pd.Series]:
    """The dataset's own truncated test trajectories and their final RUL (read once, at the end)."""
    df = _read(RAW / f"test_{subset}.txt")
    rul = pd.read_csv(RAW / f"RUL_{subset}.txt", header=None)[0]
    rul.index = np.arange(1, len(rul) + 1)
    return df, rul


def add_rul(df: pd.DataFrame, cap: int | None) -> pd.DataFrame:
    df = df.copy()
    df["rul"] = df.groupby("unit")["cycle"].transform("max") - df["cycle"]
    if cap is not None:
        df["rul"] = df["rul"].clip(upper=cap)
    return df


def make_split(units: list[int], seed: int, n_val: int, n_test: int) -> dict:
    rng = np.random.default_rng(seed)
    order = rng.permutation(np.array(sorted(units)))
    test = sorted(int(u) for u in order[:n_test])
    val = sorted(int(u) for u in order[n_test : n_test + n_val])
    train = sorted(int(u) for u in order[n_test + n_val :])
    return {"dataset": "FD001", "group": "unit", "seed": seed, "train": train, "val": val, "test": test}


def load_split() -> dict:
    return json.loads(SPLIT_FILE.read_text())


def split_frames(df: pd.DataFrame, split: dict) -> dict[str, pd.DataFrame]:
    return {k: df[df.unit.isin(split[k])].copy() for k in ("train", "val", "test")}

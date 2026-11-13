"""Block 1/2 data pipeline: raw FD001 -> capped RUL -> window features on all 21 sensors ->
memory-mapped arrays per split. Also writes the sensor sets of each experimental arm, derived from
the TRAIN split only (data/splits/arms.json), and the Java parity fixture.

Run: python model/pipeline.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from data import SENSORS, add_rul, load_official_test, load_split, load_train, split_frames  # noqa: E402
from features import CONFIG, PROCESSED, WINDOW, build_feature_frame, feature_names, save_memmap, window_features_1d  # noqa: E402

ARMS_FILE = ROOT / "data" / "splits" / "arms.json"
FIXTURE = ROOT / "tests" / "fixtures" / "window_features_engine1.json"
CAP = int(CONFIG["label"]["cap"])


def derive_arms(train_feats, train_raw) -> dict:
    """Sensor sets per arm, from train engines only (never val or test)."""
    std = train_raw[SENSORS].std(ddof=0)
    informative = [s for s in SENSORS if std[s] > 1e-6]
    rho = {}
    for s in informative:
        rho[s] = abs(float(train_feats[f"{s}_mean"].corr(train_feats["rul"], method="spearman")))
    ranked = sorted(informative, key=lambda s: (-rho[s], int(s[1:])))
    reduced8 = sorted(ranked[:8], key=lambda s: int(s[1:]))
    return {
        "derived_from": "train split only",
        "full21": SENSORS,
        "informative15": informative,
        "reduced8": reduced8,
        "spearman_abs_rho_window_mean_vs_rul_train": {s: round(rho[s], 4) for s in ranked},
    }


def main() -> None:
    raw = add_rul(load_train(), cap=CAP)
    split = load_split()
    frames = split_frames(raw, split)
    feats = {k: build_feature_frame(v, SENSORS, WINDOW) for k, v in frames.items()}

    arms = derive_arms(feats["train"], frames["train"])
    ARMS_FILE.write_text(json.dumps(arms, indent=2))

    cols = feature_names(SENSORS)
    meta = {"window": WINDOW, "cap": CAP, "feature_names": cols, "splits": {}}
    for name, f in feats.items():
        save_memmap(f"{name}_X", f[cols].to_numpy(dtype=np.float64))
        save_memmap(f"{name}_y", f["rul"].to_numpy(dtype=np.float64))
        save_memmap(f"{name}_unit", f["unit"].to_numpy(dtype=np.int32))
        save_memmap(f"{name}_cycle", f["cycle"].to_numpy(dtype=np.int32))
        meta["splits"][name] = {"rows": int(len(f)), "engines": int(f.unit.nunique())}

    # Official benchmark: features for the truncated test trajectories; only the last row per engine is scored.
    off, off_rul = load_official_test()
    off_feats = build_feature_frame(off, SENSORS, WINDOW)
    last = off_feats.groupby("unit").tail(1).sort_values("unit")
    save_memmap("official_last_X", last[cols].to_numpy(dtype=np.float64))
    save_memmap("official_last_y", off_rul.loc[last.unit.to_numpy()].to_numpy(dtype=np.float64))
    save_memmap("official_last_unit", last.unit.to_numpy(dtype=np.int32))
    meta["splits"]["official_last"] = {"rows": int(len(last)), "engines": int(last.unit.nunique())}
    (PROCESSED / "meta.json").write_text(json.dumps(meta, indent=2))

    # Java parity fixture: engine 1, first 40 cycles, all 21 sensors, raw values and the expected features.
    e1 = raw[raw.unit == 1].sort_values("cycle").head(40)
    fixture = {
        "window": WINDOW,
        "sensors": SENSORS,
        "cycles": e1.cycle.tolist(),
        "raw": [[float(v) for v in row] for row in e1[SENSORS].to_numpy()],
        "expected": {s: window_features_1d(e1[s].to_numpy(), WINDOW).tolist() for s in SENSORS},
        "expected_layout": "expected[sensor][row] = [mean, std, slope]",
    }
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(fixture))

    print(json.dumps({"arms": {k: arms[k] for k in ("informative15", "reduced8")}, "splits": meta["splits"]}, indent=2))


if __name__ == "__main__":
    main()

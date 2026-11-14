"""Offline simulator of the Java AlertEngine, used to design the trend rule on VALIDATION engines.

It replays the deployed model's predictions (sklearn, equal to the ONNX model within 1e-4) through the
same open / stay-open / close-after-K-clear-readings logic as service/.../alerts/AlertEngine.java.
Cross-check: with the service's settings it must reproduce results/alert_replay_val.json exactly.

    python model/alert_sim.py
"""
from __future__ import annotations

import json
import re
import pickle
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from data import SENSORS, add_rul, load_split, load_train, split_frames  # noqa: E402
from features import WINDOW, build_feature_frame, feature_names  # noqa: E402
from train import checkpoint_path, truncated  # noqa: E402


@dataclass
class Rules:
    warning_below: float = 60
    critical_below: float = 30
    hysteresis: float = 10
    close_after: int = 5
    trend: str = "drop"          # "drop" (endpoint difference), "slope" (OLS slope), or "none"
    trend_drop: float = 20       # drop: fire when RUL fell more than this ...
    trend_window: int = 10       # ... over this many readings (slope: fit over this many readings)
    trend_slope: float = -2.0    # slope: fire when the fitted slope is below this (cycles per reading)
    trend_clear_slope: float = -1.5
    min_window_rows: int = 1     # trend may fire only once the feature window has this many rows
    warmup_rows: int = 1         # no rule may OPEN an alert before the feature window has this many rows


def simulate(ruls: np.ndarray, window_rows: np.ndarray, r: Rules) -> list[dict]:
    recent: list[float] = []
    open_: dict[str, dict] = {}
    streak = {"WARNING": 0, "CRITICAL": 0}
    alerts: list[dict] = []
    for i, (rul, wrows) in enumerate(zip(ruls, window_rows)):
        cycle = i + 1
        recent.append(float(rul))
        keep = r.trend_window + 1 if r.trend == "drop" else r.trend_window
        recent = recent[-keep:]
        firing = {"WARNING": [], "CRITICAL": []}
        clear = {"WARNING": True, "CRITICAL": True}
        if rul < r.critical_below:
            firing["CRITICAL"].append("rul_threshold")
        if rul < r.critical_below + r.hysteresis:
            clear["CRITICAL"] = False
        if rul < r.warning_below:
            firing["WARNING"].append("rul_threshold")
        if rul < r.warning_below + r.hysteresis:
            clear["WARNING"] = False
        if r.trend == "drop" and len(recent) > r.trend_window and wrows >= r.min_window_rows:
            if recent[0] - rul > r.trend_drop:
                firing["WARNING"].append("rul_trend")
                clear["WARNING"] = False
        if r.trend == "slope" and len(recent) >= r.trend_window and wrows >= r.min_window_rows:
            slope = float(np.polyfit(np.arange(len(recent)), recent, 1)[0])
            if slope < r.trend_slope:
                firing["WARNING"].append("rul_trend")
            if slope < r.trend_clear_slope:
                clear["WARNING"] = False
        for sev in ("WARNING", "CRITICAL"):
            if sev not in open_:
                if firing[sev] and wrows >= r.warmup_rows:
                    a = {"severity": sev, "rule": "rul_trend" if firing[sev][0] == "rul_trend" else "rul_threshold",
                         "opened_cycle": cycle, "closed_cycle": None}
                    alerts.append(a)
                    open_[sev] = a
                    streak[sev] = 0
            else:
                streak[sev] = streak[sev] + 1 if clear[sev] else 0
                if streak[sev] >= r.close_after:
                    open_[sev]["closed_cycle"] = cycle
                    del open_[sev]
                    streak[sev] = 0
    return alerts


def deployed_predictions(split: str) -> dict[int, tuple[np.ndarray, np.ndarray, int]]:
    meta = json.loads((ROOT / "service" / "src" / "main" / "resources" / "models" / "rul.json").read_text())
    with open(checkpoint_path(meta["arm"], meta["seed"]), "rb") as f:
        model = truncated(pickle.load(f)["model"], meta["n_estimators"])
    raw = add_rul(load_train(), cap=None)
    frame = split_frames(raw, load_split())[split]
    out = {}
    for u, g in frame.groupby("unit"):
        f = build_feature_frame(g, SENSORS, WINDOW)
        X = f[meta["feature_names"]].to_numpy()
        pred = np.clip(model.predict(X.astype(np.float32).astype(np.float64)), 0, meta["cap"])
        rows = np.minimum(np.arange(1, len(g) + 1), WINDOW)
        out[int(u)] = (pred, rows, int(g.cycle.max()))
    return out


def evaluate(preds, r: Rules) -> dict:
    passes, warn_lead, crit_lead, n_alerts, per = 0, [], [], 0, {}
    for u, (pred, rows, life) in preds.items():
        al = simulate(pred, rows, r)
        sev = [a["severity"] for a in al]
        per[u] = al
        passes += sev == ["WARNING", "CRITICAL"]
        n_alerts += len(al)
        warn_lead += [life - a["opened_cycle"] for a in al if a["severity"] == "WARNING"]
        crit_lead += [life - a["opened_cycle"] for a in al if a["severity"] == "CRITICAL"]
    return {"engines": len(preds), "passing": passes, "alerts": n_alerts,
            "first_warning_true_rul_mean": round(float(np.mean([life - next(a["opened_cycle"] for a in per[u] if a["severity"] == "WARNING")
                                                               for u, (_, _, life) in preds.items() if any(a["severity"] == "WARNING" for a in per[u])])), 1),
            "critical_true_rul_mean": round(float(np.mean(crit_lead)), 1) if crit_lead else None,
            "critical_true_rul_min": int(min(crit_lead)) if crit_lead else None, "per_engine": per}


SERVICE_RULES = {  # what the Java service runs; keep in sync with application.yml (checked below)
    "warning-below": 60, "critical-below": 30, "trend-window": 30, "trend-slope": -2.0, "trend-clear-slope": -1.5,
    "min-window-rows": 30, "close-after": 5, "hysteresis": 10}


def service_rules() -> Rules:
    yml = (ROOT / "service" / "src" / "main" / "resources" / "application.yml").read_text()
    for k, v in SERVICE_RULES.items():
        assert re.search(rf"^\s+{k}: {re.escape(str(v))}\b", yml, re.M), f"application.yml {k} != {v}"
    return Rules(trend="slope", trend_window=30, trend_slope=-2.0, trend_clear_slope=-1.5, min_window_rows=30, warmup_rows=30)


def cross_check(preds, java_file: Path, rules: Rules) -> int:
    """Number of engines whose alert list differs between the Java service run and the simulator."""
    java = json.loads(java_file.read_text())
    sim = evaluate(preds, rules)
    mismatches = 0
    for e in java["engines"]:
        j = [(a["severity"], a["rule"], a["opened_cycle"], a["closed_cycle"] or None) for a in e["alerts"]]
        s = [(a["severity"], a["rule"], a["opened_cycle"], a["closed_cycle"]) for a in sim["per_engine"][e["unit"]]]
        if j != s:
            mismatches += 1
            print("MISMATCH", e["unit"], "\n java", j, "\n sim ", s)
    print(f"cross-check {java_file.name} vs simulator: {len(java['engines']) - mismatches}/{len(java['engines'])} engines identical")
    return mismatches


def main() -> None:
    preds = deployed_predictions("val")
    # 1. cross-check against the Java service, if a run with the current settings exists
    mismatches = None
    java_file = ROOT / "results" / "alert_replay_val.json"
    if java_file.exists() and "--check" in sys.argv:
        mismatches = cross_check(preds, java_file, service_rules())

    # 2. candidate trend rules, judged on validation only
    candidates = {
        "original: drop>20 over 10": Rules(),
        "threshold only (no trend)": Rules(trend="none"),
        "drop>20 over 10, full window": Rules(min_window_rows=30),
        "drop>30 over 20, full window": Rules(trend_drop=30, trend_window=20, min_window_rows=30),
        "slope<-2 over 20, full window": Rules(trend="slope", trend_window=20, trend_slope=-2.0, trend_clear_slope=-1.5, min_window_rows=30),
        "slope<-2.5 over 20, full window": Rules(trend="slope", trend_window=20, trend_slope=-2.5, trend_clear_slope=-1.5, min_window_rows=30),
        "slope<-3 over 20, full window": Rules(trend="slope", trend_window=20, trend_slope=-3.0, trend_clear_slope=-2.0, min_window_rows=30),
        "slope<-2 over 30, full window": Rules(trend="slope", trend_window=30, trend_slope=-2.0, trend_clear_slope=-1.5, min_window_rows=30),
        "slope<-2 over 30 + 30-row warm-up": Rules(trend="slope", trend_window=30, trend_slope=-2.0, trend_clear_slope=-1.5, min_window_rows=30, warmup_rows=30),
        "threshold only + 30-row warm-up": Rules(trend="none", warmup_rows=30),
    }
    chosen_name = "slope<-2 over 30 + 30-row warm-up"
    table = {}
    for name, r in candidates.items():
        res = evaluate(preds, r)
        trend_alerts = sum(a["rule"] == "rul_trend" for al in res["per_engine"].values() for a in al)
        table[name] = {k: v for k, v in res.items() if k != "per_engine"} | {"trend_opened": trend_alerts}
        print(f"{name:34s} pass {res['passing']:2d}/{res['engines']}  alerts {res['alerts']:3d}  trend-opened {trend_alerts:2d}  "
              f"first WARNING at true RUL {res['first_warning_true_rul_mean']}  CRITICAL at {res['critical_true_rul_mean']} (min {res['critical_true_rul_min']})")
    out = ROOT / "results" / "alert_rule_design_val.json"
    prev = json.loads(out.read_text()) if out.exists() else {}
    record = {"designed_on": "validation engines only", "chosen": chosen_name, "candidates": table,
              "cross_check_mismatches": mismatches if mismatches is not None else prev.get("cross_check_mismatches"),
              "history": ("The pre-chosen rule (endpoint drop > 20 over 10 readings) passed the stage 4 check on 2 of 15 validation "
                          "engines in the Java service: it fired on prediction jitter. The simulator also exposed a Java bug (the "
                          "first score was counted twice when the engine rebuilt its state). Both were fixed before the test split was replayed.")}
    out.write_text(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()

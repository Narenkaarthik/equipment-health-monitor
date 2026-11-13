"""Metrics shared by every run. The headline is RMSE on capped RUL; the rest are secondary."""
from __future__ import annotations

import numpy as np

WARNING_BELOW = 60
CRITICAL_BELOW = 30


def rmse(y, p) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.sqrt(np.mean((p - y) ** 2)))


def mae(y, p) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.mean(np.abs(p - y)))


def nasa_score(y, p) -> float:
    """PHM08 asymmetric score, averaged per row: late predictions (p > y) cost more than early ones."""
    d = np.asarray(p, float) - np.asarray(y, float)
    s = np.where(d < 0, np.exp(-d / 13.0) - 1.0, np.exp(d / 10.0) - 1.0)
    return float(np.mean(s))


def status_of(rul) -> np.ndarray:
    r = np.asarray(rul, float)
    return np.where(r < CRITICAL_BELOW, 2, np.where(r < WARNING_BELOW, 1, 0))  # 0 HEALTHY, 1 WARNING, 2 CRITICAL


def status_metrics(y, p) -> dict:
    """Accuracy (misleading: HEALTHY dominates), macro-F1 and CRITICAL recall of the derived status."""
    t, q = status_of(y), status_of(p)
    acc = float(np.mean(t == q))
    f1s = []
    for c in (0, 1, 2):
        tp = np.sum((t == c) & (q == c))
        fp = np.sum((t != c) & (q == c))
        fn = np.sum((t == c) & (q != c))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    crit = np.sum((t == 2) & (q == 2)) / max(np.sum(t == 2), 1)
    return {"status_acc": acc, "status_f1_macro": float(np.mean(f1s)), "critical_recall": float(crit),
            "healthy_share": float(np.mean(t == 0))}


def all_metrics(y, p) -> dict:
    m = {"rmse": rmse(y, p), "mae": mae(y, p), "nasa": nasa_score(y, p)}
    m.update(status_metrics(y, p))
    return m

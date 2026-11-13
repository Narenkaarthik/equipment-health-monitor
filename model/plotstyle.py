"""Shared matplotlib style for every figure in the project.

Rules applied (from the project's chart guidance):
* categorical hues in a fixed order, never cycled past the list;
* one hue, light-to-dark, for magnitude; status colours are reserved for status;
* thin marks, recessive grid, direct labels where they help, never a dual axis.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Categorical slots in fixed order (light surface).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
# Sequential blue ramp, light -> dark (steps 250..700).
SEQUENTIAL = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
# Reserved status palette.
STATUS = {"HEALTHY": "#0ca30c", "WARNING": "#fab219", "CRITICAL": "#d03b3b"}
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"

# Fixed colour per experimental arm so an arm keeps its colour in every figure.
ARM_COLORS = {
    "full21": SERIES[0],
    "informative14": SERIES[2],
    "reduced8": SERIES[1],
    "trivial_mean": MUTED,
    "ridge": SERIES[6],
}


def apply() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": AXIS,
            "axes.labelcolor": INK_2,
            "axes.titlecolor": INK,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelcolor": INK_2,
            "ytick.labelcolor": INK_2,
            "lines.linewidth": 1.6,
            "lines.markersize": 5,
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "figure.dpi": 150,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "axes.prop_cycle": matplotlib.cycler(color=SERIES),
        }
    )


def save(fig, path) -> None:
    """Save as PNG and PDF side by side (PDF for LaTeX, PNG for Markdown)."""
    import os

    base, _ = os.path.splitext(str(path))
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    fig.savefig(base + ".png")
    fig.savefig(base + ".pdf")
    plt.close(fig)

"""Generate showcase/: seven social cards (1080x1080), a carousel PDF of them, a banner (1584x396), copies of the
key figures and both PDFs. Every number on a card comes from results/numbers.json.

    python model/showcase.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
import plotstyle  # noqa: E402

import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

OUT = ROOT / "showcase"
CARDS = OUT / "cards"
FIG = ROOT / "report" / "figures"
N = json.loads((ROOT / "results" / "numbers.json").read_text(encoding="utf-8"))
BG = "#0f1b2d"
FG = "#f0efec"
ACCENT = "#5598e7"
WARN = "#fab219"
CRIT = "#e66767"
MUTED = "#a9b4c2"
REPO = "github.com/Narenkaarthik/equipment-health-monitor"


def card(i: int, title: str, lines: list[tuple[str, str, float]], image: str | None = None, big: str | None = None, big_label: str = ""):
    fig = plt.figure(figsize=(10.8, 10.8), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.07, 0.93, f"{i}/7", color=MUTED, fontsize=20, va="top")
    ax.text(0.07, 0.86, title, color=FG, fontsize=40, fontweight="bold", va="top")
    # body starts below however many lines the title takes
    y = 0.86 - 0.075 * (title.count("\n") + 1) - 0.05
    if big:
        ax.text(0.07, y, big, color=ACCENT, fontsize=110, fontweight="bold", va="top")
        ax.text(0.07, y - 0.17, big_label, color=FG, fontsize=24, va="top")
        y -= 0.26
    import textwrap

    for text, color, size in lines:
        # wrap to the card width: about 930 px of text, a glyph is about 0.6 em wide
        width = int(930 / (0.52 * size * 100 / 72))
        for k, part in enumerate(textwrap.wrap(text, width=width)):
            ax.text(0.07, y, ("   " if k else "") + part,
                    color={"fg": FG, "accent": ACCENT, "warn": WARN, "crit": CRIT, "muted": MUTED}[color], fontsize=size, va="top")
            y -= 0.0145 * size / 10 + 0.02
        y -= 0.008 * size / 10 + 0.015
    if image:
        img = mpimg.imread(FIG / image)
        top, bottom = y - 0.01, 0.08  # the image fills the space left under the text
        assert top - bottom > 0.18, f"card {i}: no room left for the image"
        iax = fig.add_axes([0.07, bottom, 0.86, top - bottom])
        iax.imshow(img)
        iax.set_axis_off()
    assert y > 0.08, f"card {i}: text runs into the footer (y={y:.3f})"
    ax.text(0.07, 0.035, REPO, color=MUTED, fontsize=16)
    return fig


def main() -> None:
    CARDS.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    figs = [
        card(1, "I built a real-time engine\nhealth monitor, then asked\nif it needs fewer sensors.",
             [("Java 21 · Spring Boot · Kafka · PostgreSQL · Redis", "muted", 19),
              ("ONNX model in the loop · live dashboard · k6 load tests", "muted", 19),
              ("The data: NASA C-MAPSS, a simulated turbofan benchmark", "fg", 19)], image="alert_timeline.png"),
        card(2, "The question, written\ndown before any result",
             [("Can 8 of the 21 sensors predict remaining", "fg", 26), ("useful life as well as all 21?", "fg", 26),
              (f"Non-inferiority margin: {N['margin']} cycle of RMSE", "accent", 26),
              (f"{N['n_seeds']} seeds per arm · engine-level split · test read once", "muted", 22),
              ("Split, model, grid, selection rule, seeds: all frozen", "muted", 22), ("in a committed config file first.", "muted", 22)]),
        card(3, "Pre-registered answer: no.", [
            (f"All 21 sensors: {N['main_gbr_full21_test_rmse']} cycles RMSE", "fg", 28),
            (f"8 ranked sensors: {N['main_gbr_reduced8_test_rmse']} cycles RMSE", "warn", 28),
            (f"So the service ships all 21, as the pre-registered rule says.", "muted", 22)],
            big=f"+{N['hyp_gap']}", big_label=f"cycles worse, against a {N['margin']}-cycle margin"),
        card(4, "But it's which 8,\nnot how many.", [
            (f"8 picked by forward selection: +{N['greedy8_gap']} (inside the margin)", "accent", 18),
            (f"8 lowest-ranked sensors: +{N['worst8_gap']}", "fg", 18),
            (f"The ranked 8 move together: correlation {N['redundancy_reduced8']}", "warn", 18),
            ("(post hoc: a hypothesis for the next experiment)", "muted", 18)], image="which_eight.png"),
        card(5, "The recipe was as big\nas the effect.", [
            (f"Window 30 to 60 readings: {N['window_effect_full21']} cycles better", "fg", 21),
            (f"Sensor gap at window 10 / 30 / 60:", "fg", 21),
            (f"{N['gap_w10']} / {N['hyp_gap']} / {N['gap_w60']} cycles", "accent", 18),
            ("The verdict holds everywhere; its size does not.", "muted", 19)], image="recipe_sensitivity.png"),
        card(6, "Kill the processor\nmid-stream. Lose nothing.", [
            (f"{N['restart_readings_rows']} readings stored, {N['restart_health_scores_rows']} scored, of {N['restart_file_rows']}", "fg", 23),
            (f"Scores equal an uninterrupted run (max diff {N['restart_max_diff']})", "fg", 22),
            (f"Alerts identical on all {N['restart_machines']} machines", "fg", 22),
            (f"Held-out engines to failure: {N['alert_replay_test_engines_passing']}/{N['alert_replay_test_engines']} give one WARNING, then one CRITICAL", "accent", 22),
            (f"CRITICAL opens {N['alert_replay_test_mean_true_rul_at_critical']} cycles before failure on average", "muted", 20)]),
        card(7, "The model was the\nsmall part.", [
            ("Bugs caught by testing the system, not the model:", "fg", 22),
            ("· an alert rule that fired on prediction jitter", "warn", 20),
            ("· a score counted twice after a restart", "warn", 20),
            ("· a window saved before its score (crash = lost score)", "warn", 20),
            ("· tests leaking state into the dev Redis", "warn", 20),
            (f"· a leaky row split: {N['rowsplit_optimism_pct']}% too optimistic", "warn", 20),
            ("Paper, tutorial, code and every number: open.", "accent", 22)]),
    ]
    with PdfPages(OUT / "carousel.pdf") as pdf:
        for i, f in enumerate(figs, start=1):
            f.savefig(CARDS / f"card_{i}.png", facecolor=BG)
            pdf.savefig(f, facecolor=BG)
            plt.close(f)

    # banner 1584x396
    fig = plt.figure(figsize=(15.84, 3.96), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.text(0.04, 0.70, "Real-time equipment monitoring", color=FG, fontsize=30, fontweight="bold", va="center")
    ax.text(0.04, 0.44, "Java · Spring Boot · Kafka · ONNX · PostgreSQL · Redis", color=MUTED, fontsize=20, va="center")
    ax.text(0.04, 0.22, f"{N['main_gbr_full21_test_rmse']} cycles RMSE · pre-registered · crash-tested", color=ACCENT, fontsize=20, va="center")
    img = mpimg.imread(FIG / "which_eight.png")
    iax = fig.add_axes([0.70, 0.08, 0.27, 0.84])
    iax.imshow(img)
    iax.set_axis_off()
    fig.savefig(OUT / "banner.png", facecolor=BG)
    plt.close(fig)

    (OUT / "figures").mkdir(exist_ok=True)
    for name in ("main_test_rmse", "which_eight", "recipe_sensitivity", "alert_timeline", "embeddings", "loadtest", "sensor_importance"):
        src = FIG / f"{name}.png"
        if src.exists():
            shutil.copy(src, OUT / "figures" / src.name)
    for pdf in (ROOT / "report" / "paper.pdf", ROOT / "learn" / "Learn.pdf"):
        if pdf.exists():
            shutil.copy(pdf, OUT / pdf.name)
    print("showcase written:", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()

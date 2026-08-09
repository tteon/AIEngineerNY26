#!/usr/bin/env python3
"""The one-page trade-off: difficulty across, latency and accuracy stacked, two models.

The grammar the deck's overview established — difficulty panels, SF on x — extended one
row and one dimension: the top row is the median request's DB share (log y, 1 s budget
line), the bottom row is accuracy, and within every panel the two model families share
the canvas (color = stack, marker/line = model). Reading it is one motion: pick a
difficulty, go down a column, and the trade-off at every scale is in front of you —
plus whether it survives a model change.

naive/engineered stacks (the composite before/after), because the chain arms were
measured on one family only. gpt-oss: 12-15 episodes per difficulty cell; DeepSeek:
4-5 (one repeat) — the thin cells are drawn, not hidden, and n is on the chart.

  uv run python scripts/plot_tradeoff_onepage.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
STACK_COLOR = {"naive": "#c2410c", "engineered": "#2a78d6"}
MODEL_MARKER = {"gpt-oss-120b": "o", "DeepSeek-V3.2": "^"}
MODEL_LINE = {"gpt-oss-120b": "-", "DeepSeek-V3.2": (0, (4, 2.4))}
DIFFS = ["easy", "medium", "hard"]
SFS = [1, 10, 100]
X = {1: 0, 10: 1, 100: 2}
INK, MUTED, GRID = "#12151a", "#6b7684", "#e5e8ec"
SLO_MS = 1000.0

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "figure.facecolor": "white", "savefig.facecolor": "white",
})


def load(pattern: str):
    return json.loads(Path(sorted(glob.glob(str(REPO / pattern)))[-1]).read_text())["episodes"]


def main() -> None:
    data = {"gpt-oss-120b": load("results/before_after_full_*.json"),
            "DeepSeek-V3.2": load("results/deepseek_agg_*.json")}

    fig, axes = plt.subplots(2, 3, figsize=(11.8, 7.2), sharex=True)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.80, bottom=0.06,
                        hspace=0.18, wspace=0.22)

    for col, diff in enumerate(DIFFS):
        axT, axB = axes[0][col], axes[1][col]
        for model, eps in data.items():
            for stack in ("naive", "engineered"):
                xs, lat, acc = [], [], []
                for sf in SFS:
                    cell = [e for e in eps if e["stack"] == stack and e["sf"] == sf
                            and e["difficulty"] == diff]
                    if not cell:
                        continue
                    dbms = sorted(e["db_ms"] for e in cell)
                    xs.append(X[sf])
                    lat.append(max(dbms[len(dbms) // 2], 0.5))
                    acc.append(sum(1 for e in cell if e["score_correct"]) / len(cell))
                for ax, ys in ((axT, lat), (axB, acc)):
                    ax.plot(xs, ys, linestyle=MODEL_LINE[model],
                            color=STACK_COLOR[stack], linewidth=1.6, alpha=0.9,
                            zorder=2)
                    ax.plot(xs, ys, marker=MODEL_MARKER[model], markersize=5.8,
                            markerfacecolor=STACK_COLOR[stack],
                            markeredgecolor="white", markeredgewidth=1.0,
                            linestyle="", zorder=3)
        axT.axhline(SLO_MS, color="#b91c1c", linewidth=1.0, linestyle=(0, (5, 4)),
                    zorder=1, alpha=0.75)
        axT.set_yscale("log")
        axT.set_ylim(0.4, 60000)
        axT.set_title(diff, fontsize=11, weight="bold", color=INK, loc="left", pad=6)
        axB.set_ylim(0, 1.05)
        axB.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        axB.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
        for ax in (axT, axB):
            ax.set_xticks(range(3))
            ax.set_xticklabels(["SF1", "SF10", "SF100"], fontsize=8.6)
            ax.grid(axis="y", color=GRID, linewidth=0.6)
            ax.set_axisbelow(True)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.tick_params(length=0, labelsize=7.8)

    axes[0][0].set_ylabel("request DB share, p50 (ms, log)", fontsize=8.6, color=MUTED)
    axes[1][0].set_ylabel("episodes matching gold", fontsize=8.6, color=MUTED)
    axes[0][0].annotate("1 s budget", xy=(0.03, SLO_MS),
                        xycoords=("axes fraction", "data"), fontsize=7.4,
                        color="#b91c1c", va="bottom", ha="left")

    handles = [
        plt.Line2D([], [], color=STACK_COLOR["naive"], marker="s", linestyle="",
                   markersize=6, label="naive stack"),
        plt.Line2D([], [], color=STACK_COLOR["engineered"], marker="s", linestyle="",
                   markersize=6, label="engineered stack"),
        plt.Line2D([], [], color=INK, marker="o", linestyle="-", markersize=5.4,
                   label="gpt-oss-120b (12-15 eps/cell)"),
        plt.Line2D([], [], color=INK, marker="^", linestyle=(0, (4, 2.4)),
                   markersize=5.4, label="DeepSeek-V3.2 (4-5 eps/cell, SF1·SF100)"),
    ]
    fig.legend(handles=handles, frameon=False, fontsize=8.4, ncol=4,
               loc="upper left", bbox_to_anchor=(0.06, 0.875))
    fig.suptitle("Latency and accuracy against scale, by difficulty — two model "
                 "families on the same interface", fontsize=13, weight="bold",
                 x=0.03, ha="left", y=0.965, color=INK)
    fig.text(0.03, 0.905,
             "Columns: question difficulty. Top: the median request\'s DB time "
             "(1 s budget dashed). Bottom: share of episodes matching gold. "
             "Color = stack, marker/dash = model family.",
             fontsize=8.4, color=MUTED, ha="left", va="top")
    out = REPO / "figures/tradeoff-onepage.svg"
    fig.savefig(out)
    fig.savefig("/tmp/claude-1000/-home-hadry-lab-AIsummit26/e438afef-9ffb-42c3-ae19-f7273ba469ed/scratchpad/tradeoff-onepage.png", dpi=100)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

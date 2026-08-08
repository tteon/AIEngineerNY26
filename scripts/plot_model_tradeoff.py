#!/usr/bin/env python3
"""The model facet of the trade-off: the same interface, two model families.

Companion to AIsummit26's figures/slo-tradeoff.svg. Same canvas grammar — accuracy up,
latency across (log), a budget line — but the comparison is naive vs engineered stacks on
gpt-oss-120b and DeepSeek-V3.2. Latency is the episode's DB share, p50 (the sum of the
request's executed calls): pooling individual calls buries the story, because the median
engineered episode at SF100 spends 357 ms in the database while the pooled-call median
sits at 2 s — the expensive questions contribute their many expensive calls and drown
the typical request. Replay data does not exist for these stacks, and at this n a median
is honest where a p99 would not be. Lines connect SF1 → SF100 per (stack, model).

The chart's sentence: on gpt-oss the engineered stack buys accuracy and holds the
per-call budget as the graph grows; on DeepSeek the accuracy gap collapses — the
interface deltas are model-contingent, so the interface is engineered per model, not
assumed from one.

  uv run python scripts/plot_model_tradeoff.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
STACK_COLOR = {"naive": "#c2410c", "engineered": "#2a78d6"}   # validated pair (CVD-safe)
MODEL_MARKER = {"gpt-oss-120b": "o", "DeepSeek-V3.2": "^"}
MODEL_LINE = {"gpt-oss-120b": "-", "DeepSeek-V3.2": (0, (4, 2.4))}
SFS = [1, 100]
INK, MUTED, GRID = "#12151a", "#6b7684", "#e5e8ec"
BUDGET_MS = 1000.0

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "figure.facecolor": "white", "savefig.facecolor": "white",
})


def cells(path: str, model: str):
    eps = json.loads(Path(path).read_text())["episodes"]
    out = {}
    for stack in ("naive", "engineered"):
        for sf in SFS:
            cell = [e for e in eps if e["stack"] == stack and e["sf"] == sf]
            if not cell:
                continue
            dbms = sorted(e["db_ms"] for e in cell)
            out[(stack, sf)] = {
                "p50": max(dbms[len(dbms) // 2], 1.0),
                "acc": sum(1 for e in cell if e["score_correct"]) / len(cell),
                "n_eps": len(cell), "model": model,
            }
    return out


def main() -> None:
    gpt = cells(sorted(glob.glob(str(REPO / "results/before_after_full_*.json")))[-1],
                "gpt-oss-120b")
    ds = cells(sorted(glob.glob(str(REPO / "results/deepseek_agg_*.json")))[-1],
               "DeepSeek-V3.2")

    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    fig.subplots_adjust(left=0.09, right=0.975, top=0.775, bottom=0.11)

    ax.axvline(BUDGET_MS, color="#b91c1c", linewidth=1.1, linestyle=(0, (5, 4)),
               zorder=1, alpha=0.75)
    ax.annotate("1 s — request budget, DB share alone", xy=(BUDGET_MS, 0.53),
                fontsize=7.8, color="#b91c1c", ha="right", va="bottom", rotation=90,
                xytext=(-4, 0), textcoords="offset points")

    for model, data in (("gpt-oss-120b", gpt), ("DeepSeek-V3.2", ds)):
        for stack in ("naive", "engineered"):
            pts = [(data[(stack, sf)]["p50"], data[(stack, sf)]["acc"], sf)
                   for sf in SFS if (stack, sf) in data]
            if not pts:
                continue
            xs, ys, sfs = zip(*pts)
            ax.plot(xs, ys, linestyle=MODEL_LINE[model], color=STACK_COLOR[stack],
                    linewidth=1.4, alpha=0.85, zorder=2)
            for x, y, sf, size in zip(xs, ys, sfs, (5.6, 8.6)):
                ax.plot([x], [y], marker=MODEL_MARKER[model], markersize=size,
                        markerfacecolor=STACK_COLOR[stack], markeredgecolor="white",
                        markeredgewidth=1.2, linestyle="", zorder=3)

    handles = [
        plt.Line2D([], [], color=STACK_COLOR["naive"], marker="s", linestyle="",
                   markersize=6, label="naive stack"),
        plt.Line2D([], [], color=STACK_COLOR["engineered"], marker="s", linestyle="",
                   markersize=6, label="engineered stack"),
        plt.Line2D([], [], color=INK, marker=MODEL_MARKER["gpt-oss-120b"],
                   linestyle="-", markersize=6, label="gpt-oss-120b (39 eps/cell)"),
        plt.Line2D([], [], color=INK, marker=MODEL_MARKER["DeepSeek-V3.2"],
                   linestyle=(0, (4, 2.4)), markersize=6,
                   label="DeepSeek-V3.2 (13 eps/cell)"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=8.2, loc="lower left")

    ax.set_xscale("log")
    ax.set_ylim(0.5, 1.02)
    ax.set_xlabel("episode DB time, p50 (ms, log) — the median request's database share",
                  fontsize=8.6, color=MUTED)
    ax.set_ylabel("episodes matching gold (share of cell)", fontsize=8.6, color=MUTED)
    ax.grid(color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0, labelsize=8)

    fig.suptitle("Same interface, two model families — accuracy vs the request's "
                 "DB share", fontsize=12.5, weight="bold", x=0.03,
                 ha="left", y=0.965, color=INK)
    fig.text(0.03, 0.905,
             "Color = stack, marker/dash = model; marker grows with scale (SF1 · SF100).\n"
             "x: the median episode's total DB time (a median exceeding the budget is "
             "strictly worse than a tail exceeding it). At this n a p50 is honest where "
             "a p99 would not be.\n"
             "gpt-oss: engineering buys accuracy AND holds the DB share near-flat. "
             "DeepSeek: both gaps collapse — interface deltas are model-contingent.",
             fontsize=8.0, color=MUTED, ha="left", va="top")
    out = REPO / "figures/model-tradeoff.svg"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out)
    fig.savefig("/tmp/claude-1000/-home-hadry-lab-AIsummit26/e438afef-9ffb-42c3-ae19-f7273ba469ed/scratchpad/model-tradeoff.png", dpi=110)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

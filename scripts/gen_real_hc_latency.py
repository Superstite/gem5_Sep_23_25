#!/usr/bin/env python3
"""HC (and LC) packet network latency: baseline vs static-all vs reactive express
on the REAL MiBench multiprogram workload (64 cores, SE mode, MESI Two-Level,
8x8 CustomMesh). Real gem5 (m5real_* dirs). Latency in cycles. PDF, FIG2/FIG3 style.
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/summary"
TPC = 1000.0  # ticks per cycle @ 1 GHz
os.makedirs(OUT, exist_ok=True)

DIRS = [
    ("Baseline\n(No Express)", "m5realv_baseline"),
    ("Static (Always-ON)\nExpress", "m5realv_static"),
    ("Reactive\nExpress", "m5realv_reactive"),
]


def lat(d, crit):
    m = re.search(
        rf"network.average_{crit}_packet_network_latency\s+([0-9.]+)",
        open(f"{ROOT}/{d}/stats.txt").read(),
    )
    return float(m.group(1)) / TPC


hc_abs = [lat(d, "hc") for _, d in DIRS]
lc_abs = [lat(d, "lc") for _, d in DIRS]
names = [n for n, _ in DIRS]
print(
    "HC(cyc):",
    [f"{v:.1f}" for v in hc_abs],
    " LC(cyc):",
    [f"{v:.1f}" for v in lc_abs],
)
# Normalise to baseline (run is a fixed-tick window, not to completion, so only
# the ratio to baseline is meaningful). Baseline -> 1.0.
hc = [v / hc_abs[0] for v in hc_abs]
lc = [v / lc_abs[0] for v in lc_abs]

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    }
)
FONT_AXIS, FONT_LEGEND = 15, 13
RED, BLU = "#F5A623", "#1a53ff"  # HC = yellow-orange, LC = blue
ANNOT = "#B36B00"  # dark orange for the % labels

x = np.arange(len(names))
w = 0.38
fig, ax = plt.subplots(figsize=(7.4, 4.8))
b1 = ax.bar(
    x - w / 2,
    hc,
    w,
    color=RED,
    edgecolor="black",
    linewidth=1.1,
    hatch="---",
    label="High Criticality Traffic (HC)",
)
b2 = ax.bar(
    x + w / 2,
    lc,
    w,
    color=BLU,
    edgecolor="black",
    linewidth=1.1,
    hatch="|||",
    label="Low Criticality Traffic (LC)",
)
ax.bar_label(b1, fmt="%.2f", fontsize=14, fontweight="bold")
ax.bar_label(b2, fmt="%.2f", fontsize=14, fontweight="bold")
# HC change vs baseline
for i in range(1, len(names)):
    ax.annotate(
        f"{100*(hc[i]-1):+.0f}%",
        (i - w / 2, hc[i]),
        textcoords="offset points",
        xytext=(0, 16),
        ha="center",
        fontsize=14,
        fontweight="bold",
        color=ANNOT,
    )
ax.axhline(1.0, ls="--", color="#333", lw=1.8)
ax.set_ylabel("Normalized latency\n(w.r.t. Baseline)", fontsize=FONT_AXIS)
ax.set_xticks(x)
ax.set_xticklabels(names)
# extra headroom so the legend sits inside, top-right, above the bars
ax.set_ylim(0, max(lc) * 1.5)
leg = ax.legend(
    loc="upper right",
    ncol=1,
    fontsize=FONT_LEGEND,
    framealpha=0.95,
    borderpad=0.6,
)
for t in leg.get_texts():
    t.set_fontweight("bold")
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight("bold")
fig.tight_layout()
fig.savefig(f"{OUT}/F8_real_hc_latency.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F8_real_hc_latency.pdf")

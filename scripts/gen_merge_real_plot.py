#!/usr/bin/env python3
"""Elastic VC merging benefit on the REAL MiBench workload (new HC=1-VC layout).
Static isolation (HC=1 VC, merge off) vs elastic merge (HC borrows LC at MC).
HC + LC latency in cycles. FIG2/FIG3 bold style, PDF. Matches F13 look.
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/merge"
TPC = 1000.0
DIRS = [
    ("Static isolation\n(HC = 1 VC)", "m5realv_static"),
    ("Elastic merge\n(HC borrows LC)", "m5realv_merge"),
]


def lat(d, c):
    m = re.search(
        rf"average_{c}_packet_network_latency\s+([0-9.]+)",
        open(f"{ROOT}/{d}/stats.txt").read(),
    )
    return float(m.group(1)) / TPC


hc = [lat(d, "hc") for _, d in DIRS]
lc = [lat(d, "lc") for _, d in DIRS]
names = [n for n, _ in DIRS]
# normalise to static isolation so the (small) HC and (large) LC bars are both
# readable on one axis
hcn = [v / hc[0] for v in hc]
lcn = [v / lc[0] for v in lc]
hb = 100 * (hcn[1] - 1)
ld = 100 * (lcn[1] - 1)
print(f"HC {hb:+.1f}%  LC {ld:+.1f}%")

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    }
)
x = np.arange(2)
w = 0.38
fig, ax = plt.subplots(figsize=(7.2, 5.0))
b1 = ax.bar(
    x - w / 2,
    hcn,
    w,
    color="#1a53ff",
    edgecolor="black",
    linewidth=1.2,
    hatch="//",
    label="High Criticality Traffic (HC)",
)
b2 = ax.bar(
    x + w / 2,
    lcn,
    w,
    color="#2ca02c",
    edgecolor="black",
    linewidth=1.2,
    hatch="||",
    label="Low Criticality Traffic (LC)",
)
ax.bar_label(b1, fmt="%.2f", fontsize=11, fontweight="bold")
ax.bar_label(b2, fmt="%.2f", fontsize=11, fontweight="bold")
ax.annotate(
    f"{hb:+.1f}%",
    (1 - w / 2, hcn[1]),
    textcoords="offset points",
    xytext=(0, 20),
    ha="center",
    fontsize=12,
    fontweight="bold",
    color="#1a53ff",
)
ax.annotate(
    f"{ld:+.1f}%",
    (1 + w / 2, lcn[1]),
    textcoords="offset points",
    xytext=(0, 20),
    ha="center",
    fontsize=12,
    fontweight="bold",
    color="#217821",
)
ax.axhline(1.0, ls="--", color="#333", lw=1.8)
ax.set_xticks(x)
ax.set_xticklabels(names)
ax.set_ylim(0, 1.35)
ax.set_ylabel("Normalized latency\n(w.r.t. Static isolation)", fontsize=15)
leg = ax.legend(loc="upper right", fontsize=11, framealpha=0.95)
for t in leg.get_texts():
    t.set_fontweight("bold")
for lb in ax.get_xticklabels() + ax.get_yticklabels():
    lb.set_fontweight("bold")
fig.tight_layout()
fig.savefig(f"{OUT}/F14_merge_real.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F14_merge_real.pdf")

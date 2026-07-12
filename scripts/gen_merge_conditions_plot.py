#!/usr/bin/env python3
"""When is elastic VC merging useful? HC benefit + LC cost of merge (forced =
ceiling) vs donor load (LC rate), synthetic bursty HC + always-on express.
Reads conditions.csv. FIG2/FIG3 bold style, PDF.
"""
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/merge"
rows = list(csv.DictReader(open(f"{OUT}/conditions.csv")))
lc = [r["lc_rate"].replace("GiB/s", "") for r in rows]
hb = np.array([float(r["hc_benefit_%"]) for r in rows])
ld = np.array([float(r["lc_degr_%"]) for r in rows])

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    }
)
FA = 15
x = np.arange(len(lc))
w = 0.38
fig, ax = plt.subplots(figsize=(7.8, 4.8))
b1 = ax.bar(
    x - w / 2,
    hb,
    w,
    color="#2ca02c",
    edgecolor="black",
    linewidth=1.1,
    hatch="//",
    label="HC latency benefit",
)
b2 = ax.bar(
    x + w / 2,
    ld,
    w,
    color="#d62728",
    edgecolor="black",
    linewidth=1.1,
    hatch="\\\\",
    label="LC degradation",
)
ax.bar_label(b1, fmt="%.1f", fontsize=10, fontweight="bold")
ax.bar_label(b2, fmt="%.1f", fontsize=10, fontweight="bold")
ax.axhline(0, color="#333", lw=1.4)
ax.set_xticks(x)
ax.set_xticklabels(lc)
ax.set_xlabel("LC injection rate (GiB/s)  [donor load →]", fontsize=FA)
ax.set_ylabel("Change vs static isolation\n(%)", fontsize=FA)
leg = ax.legend(loc="upper right", fontsize=12)
for t in leg.get_texts():
    t.set_fontweight("bold")
for lb in ax.get_xticklabels() + ax.get_yticklabels():
    lb.set_fontweight("bold")
# shade the "useful" regime (light donor)
ax.axvspan(-0.5, 2.5, color="#2ca02c", alpha=0.07)
ax.text(
    1.0,
    ax.get_ylim()[1] * 0.92,
    "donor has slack\n→ merge useful",
    ha="center",
    fontsize=10,
    fontweight="bold",
    color="#217821",
)
fig.tight_layout()
fig.savefig(f"{OUT}/F12_merge_conditions.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F12_merge_conditions.pdf")

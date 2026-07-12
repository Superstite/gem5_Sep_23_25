#!/usr/bin/env python3
"""Plot the elastic-VC-merge gate sweep (real workload): HC-latency benefit vs
LC degradation for each (mc_hc_hi, mc_lc_lo) gate. Best = high HC benefit, low
LC cost (down-right). Reads gatesweep.csv. FIG2/FIG3 bold style, PDF.
"""
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/merge"

rows = list(csv.DictReader(open(f"{OUT}/gatesweep.csv")))
hb = np.array([float(r["hc_benefit_%"]) for r in rows])
ld = np.array([float(r["lc_degr_%"]) for r in rows])
lab = [
    f"{r['hc_hi']}/{('∞' if int(r['lc_lo'])>9999 else r['lc_lo'])}"
    for r in rows
]
net = hb - ld
best = int(np.argmax(net))
print("best gate:", lab[best], f"HC {hb[best]:+.2f}% LC {ld[best]:+.2f}%")

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
fig, ax = plt.subplots(figsize=(7.6, 5.2))
ax.axhline(0, color="#888", lw=1)
ax.axvline(0, color="#888", lw=1)
sc = ax.scatter(
    hb,
    ld,
    s=140,
    c=net,
    cmap="viridis",
    edgecolor="black",
    linewidth=1.2,
    zorder=3,
)
ax.scatter(
    hb[best],
    ld[best],
    s=320,
    facecolor="none",
    edgecolor="#e60000",
    linewidth=2.6,
    zorder=4,
    label="best gate",
)
for i, t in enumerate(lab):
    ax.annotate(
        t,
        (hb[i], ld[i]),
        textcoords="offset points",
        xytext=(7, 4),
        fontsize=10,
        fontweight="bold",
    )
ax.set_xlabel("HC latency benefit vs isolation (%)", fontsize=FA)
ax.set_ylabel("LC degradation vs isolation (%)", fontsize=FA)
cb = fig.colorbar(sc, ax=ax, pad=0.02)
cb.set_label("net = HC benefit − LC cost (%)", fontsize=12, fontweight="bold")
leg = ax.legend(loc="upper left", fontsize=12)
for t in leg.get_texts():
    t.set_fontweight("bold")
for lb in ax.get_xticklabels() + ax.get_yticklabels():
    lb.set_fontweight("bold")
ax.text(
    0.98,
    0.02,
    "gate = mc_hc_hi / mc_lc_lo",
    transform=ax.transAxes,
    ha="right",
    va="bottom",
    fontsize=10,
    style="italic",
)
fig.tight_layout()
fig.savefig(f"{OUT}/F11_merge_gatesweep.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F11_merge_gatesweep.pdf")

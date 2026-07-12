#!/usr/bin/env python3
"""Result plots (real gem5, read from existing m5out_merge_* dirs — no re-run):
express-link activation vs baseline, with VC merging disabled and enabled.

Honest finding baked into the data: express activation cuts HC latency ~23%;
the two-factor-gated VC merge adds ~0 on this workload (HC not VC-starved at the
influential routers, gate rarely opens); merge forced always-open is the ceiling
(~-3% over express).
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/merge"
os.makedirs(OUT, exist_ok=True)

DIRS = {
    "baseline": "m5out_merge_off_base",
    "express": "m5out_merge_off_expr",
    "express+merge": "m5out_merge_on_expr",  # two-factor gate
    "express+merge (gate forced)": "m5out_merge_force",
}


def lat(d, crit):
    txt = open(f"{ROOT}/{d}/stats.txt").read()
    m = re.search(
        rf"network.average_{crit}_packet_network_latency\s+([0-9.]+)", txt
    )
    return float(m.group(1))


HC = {k: lat(v, "hc") for k, v in DIRS.items()}
LC = {k: lat(v, "lc") for k, v in DIRS.items()}
for k in DIRS:
    print(f"{k:28s} HC={HC[k]:.0f} LC={LC[k]:.0f}")

RED, BLU = "#c44e52", "#4c72b0"
ymax = max(HC.values()) * 1.15


def grouped(ax, keys, title):
    x = np.arange(len(keys))
    w = 0.36
    b1 = ax.bar(x - w / 2, [HC[k] for k in keys], w, label="HC", color=RED)
    b2 = ax.bar(x + w / 2, [LC[k] for k in keys], w, label="LC", color=BLU)
    ax.bar_label(b1, fmt="%.0f", fontsize=8)
    ax.bar_label(b2, fmt="%.0f", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(keys, fontsize=9)
    ax.set_ylabel("Avg packet network latency (ticks)")
    ax.set_ylim(0, ymax)
    ax.set_title(title)
    ax.legend()
    base = HC[keys[0]]
    for i, k in enumerate(keys[1:], 1):
        ax.annotate(
            f"HC {100*(HC[k]/base-1):+.1f}%",
            (i, HC[k]),
            textcoords="offset points",
            xytext=(0, 16),
            ha="center",
            fontsize=9,
            color=RED,
        )


# Plot A: VC merging DISABLED -> express vs baseline
fig, ax = plt.subplots(figsize=(6.4, 4.6))
grouped(
    ax,
    ["baseline", "express"],
    "VC merging DISABLED\nexpress-link activation vs baseline",
)
fig.tight_layout()
fig.savefig(f"{OUT}/A_merge_disabled.png", dpi=140)
plt.close(fig)

# Plot B: VC merging ENABLED -> baseline vs express+merge (+ forced ceiling)
fig, ax = plt.subplots(figsize=(7.6, 4.6))
grouped(
    ax,
    ["baseline", "express+merge", "express+merge (gate forced)"],
    "VC merging ENABLED at influential routers\n"
    "(two-factor gate adds ~0; forced-open is the ceiling)",
)
fig.tight_layout()
fig.savefig(f"{OUT}/B_merge_enabled.png", dpi=140)
plt.close(fig)

# Plot C: combined HC-only, both mechanisms
fig, ax = plt.subplots(figsize=(7.6, 4.6))
keys = ["baseline", "express", "express+merge", "express+merge (gate forced)"]
cols = ["#777", RED, "#8c2d2d", "#5c1d1d"]
bars = ax.bar(range(len(keys)), [HC[k] for k in keys], color=cols)
ax.bar_label(bars, fmt="%.0f", fontsize=9)
ax.set_xticks(range(len(keys)))
ax.set_xticklabels(
    [
        "baseline",
        "express",
        "express\n+merge (gated)",
        "express\n+merge (forced)",
    ],
    fontsize=9,
)
ax.set_ylabel("Avg HC packet network latency (ticks)")
ax.set_title("HC latency: express activation (large) + VC merging (marginal)")
b = HC["baseline"]
for i, k in enumerate(keys[1:], 1):
    ax.annotate(
        f"{100*(HC[k]/b-1):+.1f}%",
        (i, HC[k]),
        textcoords="offset points",
        xytext=(0, 14),
        ha="center",
        fontsize=9,
    )
fig.tight_layout()
fig.savefig(f"{OUT}/C_combined_hc.png", dpi=140)
plt.close(fig)

print(f"\n[done] -> {OUT}")
for f in sorted(os.listdir(OUT)):
    print("   ", f)

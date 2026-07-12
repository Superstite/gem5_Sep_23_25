#!/usr/bin/env python3
"""Elastic VC merge under HC VC-STARVATION (VC0 escape, VC1 HC, VC2-3 LC).
HC has 1 data VC; merge at MC lets HC borrow the 2 LC VCs (1->3). Sweep LC rate
(donor availability); compare merge OFF vs merge FORCED. Real gem5.
"""
import csv
import os
import re
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
GEM5 = f"{ROOT}/build/X86_MESI_Two_Level/gem5.debug"
CFG = f"{ROOT}/configs/network/recon_traffic.py"
OUT = f"{ROOT}/scripts/recon_results/merge"
BASE = [
    "--duration",
    "0.1ms",
    "--hc-rate",
    "16GiB/s",
    "--high-crit-srcs",
    "0,3,10,20,29,35,48,59",
    "--epoch",
    "100",
    "--hc-burst",
    "2000ns",
    "--hc-gap",
    "6000ns",
    "--hc-warmup",
    "5000ns",
    "--routing-algo",
    "2",
    "--express-active",
    "1",
]
LC = ["0.5GiB/s", "1GiB/s", "2GiB/s", "4GiB/s"]


def run(tag, flags):
    od = f"{ROOT}/m5starvsw_{tag}"
    os.makedirs(od, exist_ok=True)
    if (
        not os.path.exists(f"{od}/stats.txt")
        or os.path.getsize(f"{od}/stats.txt") == 0
    ):
        subprocess.run(
            [GEM5, f"--outdir={od}", CFG] + BASE + flags,
            stdout=open(f"{od}/run.log", "w"),
            stderr=subprocess.STDOUT,
            check=False,
        )
    txt = open(f"{od}/stats.txt").read()

    def g(k):
        m = re.search(rf"average_{k}_packet_network_latency\s+([0-9.]+)", txt)
        return float(m.group(1)) if m else float("nan")

    return g("hc"), g("lc")


rows = [("lc", "hc_iso", "hc_merge", "hc_benefit_%", "lc_degr_%")]
for lc in LC:
    tag = lc.replace("/", "").replace(".", "p")
    hc0, l0 = run(f"iso_{tag}", ["--lc-rate", lc, "--mc-merge", "0"])
    hc1, l1 = run(
        f"mrg_{tag}",
        [
            "--lc-rate",
            lc,
            "--mc-merge",
            "1",
            "--mc-hc-hi",
            "1",
            "--mc-lc-lo",
            "999999",
        ],
    )
    hb = 100 * (hc0 - hc1) / hc0
    ld = 100 * (l1 - l0) / l0
    rows.append((lc, hc0, hc1, hb, ld))
    print(
        f"LC={lc:8s} HC iso={hc0:.0f} merge={hc1:.0f} ({hb:+.1f}%) "
        f"LC degr {ld:+.1f}%",
        flush=True,
    )

with open(f"{OUT}/starv.csv", "w", newline="") as fh:
    csv.writer(fh).writerows(rows)

# ---- plot: HC latency normalized to static isolation, per LC + benefit ----
lcs = [r[0].replace("GiB/s", "") for r in rows[1:]]
hi = np.array([r[1] for r in rows[1:]])
hm = np.array([r[2] for r in rows[1:]])
hb = np.array([r[3] for r in rows[1:]])
hi_n = hi / hi  # static isolation -> 1.0
hm_n = hm / hi  # elastic merge relative to isolation
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    }
)
x = np.arange(len(lcs))
w = 0.38
fig, ax = plt.subplots(figsize=(7.8, 4.8))
b1 = ax.bar(
    x - w / 2,
    hi_n,
    w,
    color="#1a53ff",
    edgecolor="black",
    linewidth=1.1,
    hatch="//",
    label="Static isolation (HC=1 VC)",
)
b2 = ax.bar(
    x + w / 2,
    hm_n,
    w,
    color="#2ca02c",
    edgecolor="black",
    linewidth=1.1,
    hatch="\\\\",
    label="Elastic merge (HC borrows LC)",
)
ax.bar_label(b1, fmt="%.2f", fontsize=10, fontweight="bold")
ax.bar_label(b2, fmt="%.2f", fontsize=10, fontweight="bold")
for i in range(len(lcs)):
    ax.annotate(
        f"{-hb[i]:+.0f}%",
        (i + w / 2, 1.06),
        ha="center",
        va="bottom",
        fontsize=11,
        fontweight="bold",
        color="#217821",
    )
ax.axhline(1.0, ls="--", color="#333", lw=1.6)
ax.set_xticks(x)
ax.set_xticklabels(lcs)
ax.set_ylim(0, 1.32)  # headroom for legend
ax.set_xlabel("LC injection rate (GiB/s)  [donor load →]", fontsize=15)
ax.set_ylabel("Normalized HC latency\n(w.r.t. Static isolation)", fontsize=15)
leg = ax.legend(loc="upper right", fontsize=11)
for t in leg.get_texts():
    t.set_fontweight("bold")
for lb in ax.get_xticklabels() + ax.get_yticklabels():
    lb.set_fontweight("bold")
fig.tight_layout()
fig.savefig(f"{OUT}/F13_merge_starvation.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F13_merge_starvation.pdf")

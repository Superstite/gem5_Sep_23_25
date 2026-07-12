#!/usr/bin/env python3
"""Burst-sweep line graph: baseline vs reactive vs static-all HC latency as the
HC burst density varies (fixed 2000 ns burst, swept gap). Real gem5. Shades the
improvement area of each express scheme w.r.t. baseline. Bold text + bold colors.

Traffic terms (HC source cores only; LC cores stream steadily):
  burst  = ON  window: HC cores inject at the HC rate (8 GiB/s) for 2000 ns.
  gap    = OFF window: HC cores are idle (no injection) for the swept duration.
  period = burst + gap; the pattern repeats for the whole run after a warmup.
  warmup = 5000 ns initial idle so the first burst hits a steady network.
X axis = HC ON-fraction = burst/(burst+gap) [%]: fraction of time HC is bursting
  (denser bursts to the right). NOT the express "duty cycle" (which measures how
  much the express links are active).
"""
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
OUT = f"{ROOT}/scripts/recon_results/summary"
os.makedirs(OUT, exist_ok=True)

BURST = 2000
GAPS = [2000, 3000, 4000, 6000, 9000]  # ns  -> sweep burst density
BASE_LOAD = [
    "--hc-rate",
    "8GiB/s",
    "--lc-rate",
    "2GiB/s",
    "--high-crit-srcs",
    "0,3,10,20,29,35,48,59",
    "--duration",
    "0.1ms",
    "--epoch",
    "100",
    "--hc-warmup",
    "5000ns",
    "--hc-burst",
    f"{BURST}ns",
]
SCHEMES = {
    "baseline": ["--routing-algo", "1"],
    "reactive": [
        "--routing-algo",
        "2",
        "--reconfig",
        "1",
        "--reconfig-policy",
        "1",
        "--hc-hi",
        "40",
        "--hc-lo",
        "1",
    ],
    "static": [
        "--routing-algo",
        "2",
        "--express-active",
        "1",
        "--reconfig",
        "1",
        "--reconfig-policy",
        "1",
        "--hc-hi",
        "999999999",
        "--hc-lo",
        "0",
    ],
}


def run(scheme, gap):
    od = f"{ROOT}/m5bs_{scheme}_{gap}"
    os.makedirs(od, exist_ok=True)
    # Reuse a completed run if present (skip re-simulation).
    if not os.path.exists(f"{od}/stats.txt"):
        subprocess.run(
            [GEM5, f"--outdir={od}", CFG]
            + BASE_LOAD
            + ["--hc-gap", f"{gap}ns"]
            + SCHEMES[scheme],
            stdout=open(f"{od}/run.log", "w"),
            stderr=subprocess.STDOUT,
            check=False,
        )
    m = re.search(
        r"average_hc_packet_network_latency\s+([0-9.]+)",
        open(f"{od}/stats.txt").read(),
    )
    return float(m.group(1)) if m else float("nan")


data = {s: [] for s in SCHEMES}
for g in GAPS:
    for s in SCHEMES:
        v = run(s, g)
        data[s].append(v)
        print(f"gap={g:5d} {s:9s} HC={v:.0f}", flush=True)

# X axis: HC ON-fraction = fraction of time HC cores are bursting (not the
# express duty cycle). Larger = denser bursts.
on_frac = [100.0 * BURST / (BURST + g) for g in GAPS]
order = np.argsort(on_frac)
x = np.array(on_frac)[order]
base_abs = np.array(data["baseline"])[order]
# Normalise to baseline (absolute latency depends on the run window, so only the
# ratio to baseline is meaningful). Baseline -> 1.0.
reac = np.array(data["reactive"])[order] / base_abs
stat = np.array(data["static"])[order] / base_abs
base = np.ones_like(base_abs, dtype=float)

# ---- bold styling; font sizes matched to FIG2/FIG3 (gen_motivation_real.py) ----
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "axes.titleweight": "bold",
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    }
)
FONT_AXIS, FONT_LEGEND = 15, 13
C_BASE, C_REAC, C_STAT = "#000000", "#1a53ff", "#e60000"  # bold colors
fig, ax = plt.subplots(figsize=(7.0, 4.6))

# shade improvement w.r.t. baseline (blue = reactive gain; thin red band = the
# extra static gain beyond reactive). Non-overlapping -> no purple.
ax.fill_between(x, reac, base, color=C_REAC, alpha=0.15)
ax.fill_between(x, stat, reac, color=C_STAT, alpha=0.18)

ax.plot(x, base, "o-", color=C_BASE, lw=3, ms=7, label="Baseline (No Express)")
ax.plot(
    x, stat, "^-", color=C_STAT, lw=3, ms=7, label="Static (Always-ON) Express"
)
ax.plot(x, reac, "s-", color=C_REAC, lw=3, ms=7, label="Reactive Express")

ax.set_xlabel("HC ON-fraction (%)  [denser bursts →]", fontsize=FONT_AXIS)
ax.set_ylabel("Normalized HC latency\n(w.r.t. Baseline)", fontsize=FONT_AXIS)
# broken y-axis: lines sit above ~0.8, so zoom in (kills lower whitespace) and
# mark the 0->0.78 cut; top headroom leaves room for the legend above baseline.
ax.set_ylim(0.78, 1.16)
ax.set_yticks([0.8, 0.9, 1.0])
# criss-cross break marks near the bottom of the y-axis (axis truncated below)
dx, dy = 0.012, 0.012
bk = dict(transform=ax.transAxes, color="k", clip_on=False, lw=1.6)
for yb in (0.015, 0.045):
    ax.plot((-dx, dx), (yb - dy, yb + dy), **bk)
leg = ax.legend(
    loc="upper right", ncol=1, framealpha=0.96, fontsize=FONT_LEGEND
)
for t in leg.get_texts():
    t.set_fontweight("bold")
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight("bold")
fig.tight_layout()
fig.savefig(f"{OUT}/F5_burstsweep.pdf", bbox_inches="tight")  # vector PDF
print(f"\n[done] -> {OUT}/F5_burstsweep.pdf")

#!/usr/bin/env python3
"""When are express links active under the REACTIVE strategy, and at what duty?
Per-epoch express activity (fraction of the 64 routers with express ON) over
time, overlaid with HC demand so the on/off tracking is visible. Real gem5
(m5out_rl_reactive, sparse bursty W4). PDF, FIG2/FIG3 bold style.
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/summary"
LOG = f"{ROOT}/m5out_rl_reactive/run.log"
EPOCH_CYC = 100
RE = re.compile(
    r"RTRACE t=(\d+) R\d+ (?:flits|packets)=\d+ mc=\d+ hc=(\d+) "
    r"lc=\d+ hcocc=\d+ dnocc=\d+ ex=(\d+)"
)

on, tot, hc = {}, {}, {}
with open(LOG) as fh:
    for ln in fh:
        m = RE.search(ln)
        if not m:
            continue
        t, h, ex = int(m.group(1)), int(m.group(2)), int(m.group(3))
        tot[t] = tot.get(t, 0) + 1
        on[t] = on.get(t, 0) + ex
        hc[t] = hc.get(t, 0) + h

ts = sorted(tot)
ep = np.arange(len(ts))
duty = np.array([100.0 * on[t] / tot[t] for t in ts])  # % routers ON / epoch
hcd = np.array([hc[t] for t in ts], float)
hcn = 100.0 * hcd / (hcd.max() or 1)  # HC demand, normalised %
mean_duty = duty.mean()
print(
    f"epochs={len(ts)}  mean express duty={mean_duty:.1f}%  "
    f"active epochs={(duty>0).mean()*100:.0f}%"
)

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
C_EXP, C_HC = "#1a53ff", "#D7191C"

fig, ax = plt.subplots(figsize=(7.6, 4.6))
# HC demand (why express turns on) as a faint filled backdrop
ax.fill_between(
    ep,
    0,
    hcn,
    color=C_HC,
    alpha=0.16,
    zorder=1,
    label="HC demand (normalised)",
)
# express activity per epoch
ax.fill_between(ep, 0, duty, color=C_EXP, alpha=0.35, step="mid", zorder=2)
ax.plot(
    ep,
    duty,
    color=C_EXP,
    lw=1.8,
    drawstyle="steps-mid",
    zorder=3,
    label="Express active (% routers)",
)
# mean duty line
ax.axhline(
    mean_duty,
    ls="--",
    color="#000",
    lw=2,
    zorder=4,
    label=f"Mean duty = {mean_duty:.0f}%",
)

ax.set_xlabel(f"Time (epochs of {EPOCH_CYC} cycles)", fontsize=FONT_AXIS)
ax.set_ylabel("Express-link activity\n(% of routers ON)", fontsize=FONT_AXIS)
ax.set_xlim(ep[0], ep[-1])
ax.set_ylim(0, 105)
leg = ax.legend(loc="upper right", framealpha=0.92, fontsize=FONT_LEGEND)
for t in leg.get_texts():
    t.set_fontweight("bold")
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight("bold")
fig.tight_layout()
fig.savefig(f"{OUT}/F6_reactive_duty.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F6_reactive_duty.pdf")

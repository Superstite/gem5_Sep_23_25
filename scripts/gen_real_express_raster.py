#!/usr/bin/env python3
"""Space-time raster of express-routed HC traffic on the REAL MiBench workload
(reactive strategy). Router x time; cell = HC packets that router sent via
express in a 100-cycle epoch. Real gem5 (m5real_react_trace). Vector pcolormesh
(flat cells, no bitmap-smoothing artifact). PDF, FIG2/FIG3 bold style.
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/summary"
LOG = f"{ROOT}/m5real_react_trace/express.log"
BIN = 100 * 1000  # 1 epoch = 100 cycles = 100000 ticks
MC = {21, 42}

RE = re.compile(r"^\s*(\d+):.*RECONF_EXPRESS R(\d+)->")
cnt = {}
for ln in open(LOG):
    m = RE.search(ln)
    if m:
        ep = int(m.group(1)) // BIN
        r = int(m.group(2))
        cnt[(ep, r)] = cnt.get((ep, r), 0) + 1

eps = sorted({e for e, _ in cnt})
routers = sorted({r for _, r in cnt})
e0, ne = eps[0], eps[-1] - eps[0] + 1
ridx = {r: i for i, r in enumerate(routers)}
M = np.zeros((len(routers), ne))
for (e, r), c in cnt.items():
    M[ridx[r], e - e0] = c
print(
    f"routers={len(routers)} epochs={ne} total HC packets via express="
    f"{int(M.sum())}"
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
FONT_AXIS = 15
fig, ax = plt.subplots(figsize=(9.0, 5.4))
xe = e0 + np.arange(ne + 1)
ye = np.arange(len(routers) + 1)
im = ax.pcolormesh(xe, ye, M, cmap="turbo", vmin=0, vmax=M.max())
ax.invert_yaxis()
ax.set_yticks(np.arange(len(routers)) + 0.5)
ax.set_yticklabels(
    [f"R{r}" + ("  [MC]" if r in MC else "") for r in routers],
    fontsize=9,
    fontweight="bold",
)
ax.set_xlabel("Time (t: epochs of 100 cycles)", fontsize=FONT_AXIS)
ax.set_ylabel("Mesh router (Express link)", fontsize=FONT_AXIS)
for lbl in ax.get_xticklabels():
    lbl.set_fontweight("bold")
cb = fig.colorbar(im, ax=ax, pad=0.02, aspect=26)
cb.set_label(
    "HC packets routed via express / epoch", fontsize=13, fontweight="bold"
)
cb.ax.tick_params(labelsize=11)
fig.tight_layout()
fig.savefig(f"{OUT}/F10_real_express_raster.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F10_real_express_raster.pdf")

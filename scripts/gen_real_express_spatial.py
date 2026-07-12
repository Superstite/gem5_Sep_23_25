#!/usr/bin/env python3
"""Alternative to the space-time raster: SPATIAL mesh snapshots. The 8x8
CustomMesh drawn at several time instants; each cell = HC packets that router
sent via express in that window (reactive strategy, real MiBench workload).
Shows WHICH router (by physical position) carried HC on express and how the
active region migrates across the mesh over time. Real gem5. PDF, bold style.
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/summary"
LOG = f"{ROOT}/m5realv_react_trace/express.log"
MESH = 8
MC = {21, 42}
NPANEL = 6  # number of time snapshots
# Simulation length = the --max-ticks the run used (1 cycle = 1000 ticks @1GHz).
MAX_TICKS = 25_000_000  # = 25,000 cycles

RE = re.compile(r"^\s*(\d+):.*RECONF_EXPRESS R(\d+)->")
ev = []  # (tick, router)
for ln in open(LOG):
    m = RE.search(ln)
    if m:
        ev.append((int(m.group(1)), int(m.group(2))))
if not ev:
    raise SystemExit("no RECONF_EXPRESS events")
# Divide the WHOLE simulation [0, MAX_TICKS] into NPANEL equal windows.
edges = np.linspace(0, MAX_TICKS, NPANEL + 1)
grids = [np.zeros((MESH, MESH)) for _ in range(NPANEL)]
for t, r in ev:
    k = min(NPANEL - 1, int(t / MAX_TICKS * NPANEL))
    # horizontal axis = mesh ROW (r//MESH), vertical axis = mesh COLUMN (r%MESH)
    grids[k][r % MESH, r // MESH] += 1
vmax = max(g.max() for g in grids) or 1
print(f"events={len(ev)} sim_cycles={MAX_TICKS//1000} vmax={vmax:.0f}")

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
CMAP = "turbo"
edg = np.arange(MESH + 1)
fig, axes = plt.subplots(2, 3, figsize=(12.6, 7.4))
for k, ax in enumerate(axes.flat):
    # pcolormesh draws each router as a vector quad (no embedded bitmap) so
    # cells stay flat single-colour in every PDF viewer + white cell borders.
    im = ax.pcolormesh(
        edg,
        edg,
        grids[k],
        cmap=CMAP,
        vmin=0,
        vmax=vmax,
        edgecolors="white",
        linewidth=0.6,
    )
    ax.invert_yaxis()  # row 0 at top
    ax.set_aspect("equal")
    c0 = int(edges[k] // 1000)  # ticks -> cycles
    c1 = int(edges[k + 1] // 1000)
    ax.set_title(f"t = {c0}–{c1} cyc", fontsize=14, fontweight="bold")
    for r in MC:  # mark influential/MC routers (black hatch)
        ax.add_patch(
            plt.Rectangle(
                (r // MESH, r % MESH),
                1,
                1,
                fill=False,
                ec="black",
                lw=2.4,
                hatch="|||",
            )
        )
    ax.set_xticks(np.arange(MESH) + 0.5)
    ax.set_yticks(np.arange(MESH) + 0.5)
    ax.set_xticklabels(range(MESH), fontsize=13, fontweight="bold")
    ax.set_yticklabels(range(MESH), fontsize=13, fontweight="bold")
    ax.tick_params(length=0)
    # horizontal = mesh row, vertical = mesh column
    if k // 3 == 1:
        ax.set_xlabel("Mesh row", fontsize=FONT_AXIS, fontweight="bold")
    if k % 3 == 0:
        ax.set_ylabel("Mesh column", fontsize=FONT_AXIS, fontweight="bold")
cb = fig.colorbar(im, ax=axes, shrink=0.85, pad=0.02, aspect=30)
cb.set_label("HC packets via express / window", fontsize=13, fontweight="bold")
cb.ax.tick_params(labelsize=12)
fig.savefig(f"{OUT}/F9_real_express_spatial.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F9_real_express_spatial.pdf")

#!/usr/bin/env python3
"""
Motivation figure 3 (companion to FIG2_instantaneous_state) -- motivates
runtime-activated EXPRESS LINKS:

    Within ONE execution, under a CONSTANT offered load, congestion does not
    sit at a single fixed place. It roams across the mesh over time: a router
    (and the link that would relieve it) that limits traffic in one interval is
    underutilized in the next. A topology fixed at design time cannot follow
    this moving hotspot; express links must be activated at runtime.

Uses the SAME gem5 run as Fig. 2 (m5motiv_rtrace_steady:
HC 1 GiB/s + LC 2 GiB/s, non-bursty, XY routing, 8x8 CustomMesh, epoch=100 cyc).

Space-time raster: rows = the routers that are congested at some point in the
run, columns = time (epoch), colour = per-router flits/epoch (buffer pressure).
Bright cells that appear, move, and vanish show the hotspot is dynamic.

All plotted values are measured by gem5 (per-router, per-epoch ReconTrace).
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/motivation"
STEADY_LOG = f"{ROOT}/m5motiv_rtrace_steady/run.log"  # SAME run as Fig. 2
EPOCH_CYC = 100
MESH = 8
MC_ROUTERS = {21, 42}

RTRACE_RE = re.compile(r"RTRACE t=(\d+) R(\d+) (?:flits|packets)=(\d+)")

# --- parse per-router per-epoch load from the shared run -------------------
per_t = {}
with open(STEADY_LOG) as fh:
    for line in fh:
        m = RTRACE_RE.search(line)
        if not m:
            continue
        t, r, f = int(m.group(1)), int(m.group(2)), int(m.group(3))
        per_t.setdefault(t, {})[r] = f

ticks = sorted(per_t)[5:]  # drop fill transient
n_ep = len(ticks)
M = np.zeros((64, n_ep))  # router x epoch
for j, t in enumerate(ticks):
    for r, f in per_t[t].items():
        M[r, j] = f

# routers that are congested (>2x that epoch's per-router mean) in >8% of epochs
epoch_mean = M.mean(axis=0)  # mean over routers, per epoch
congested_frac = ((M > 2.0 * epoch_mean[None, :]).sum(axis=1)) / n_ep
sel = np.where(congested_frac > 0.08)[0]
# order rows by mesh column then row so the two MC corridors group together
sel = sorted(sel, key=lambda r: (r % MESH, r // MESH))
row_labels = [
    f"R{r} (r{r//MESH}c{r%MESH})" + ("  [MC]" if r in MC_ROUTERS else "")
    for r in sel
]
S = M[sel, :]  # selected rows

# count how many distinct routers ever act as the top-loaded non-sink hotspot
nonsink_top = set()
for j in range(n_ep):
    col = M[:, j].copy()
    for r in MC_ROUTERS:
        col[r] = -1
    nonsink_top.add(int(col.argmax()))
print(
    f"parsed {n_ep} epochs; {len(sel)} congested routers; "
    f"{len(nonsink_top)} distinct non-sink hotspot routers over the run"
)

# ---------------------------------------------------------------------------
# FIGURE  (style matched to Fig. 2 — bold, no title)
# ---------------------------------------------------------------------------
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "axes.linewidth": 1.4,
        "xtick.labelsize": 11,
        "ytick.labelsize": 10,
    }
)
FONT_AXIS = 13

fig, ax = plt.subplots(figsize=(7.6, 4.8))

# cap the colour scale so the moving MID-tier hotspots are visible (the two MC
# sinks are persistently hot and simply saturate the top of the scale).
vmax = float(
    np.percentile(S[np.array([r not in MC_ROUTERS for r in sel])], 99)
)
im = ax.imshow(
    S,
    aspect="auto",
    cmap="turbo",
    vmin=0,
    vmax=vmax,
    origin="upper",
    interpolation="nearest",
    extent=[0, n_ep, len(sel) - 0.5, -0.5],
)

ax.set_yticks(range(len(sel)))
ax.set_yticklabels(row_labels, fontsize=9)
ax.set_xlabel(
    f"Time (epoch = {EPOCH_CYC} cycles)", fontsize=FONT_AXIS, labelpad=4
)
ax.set_ylabel("Mesh router", fontsize=FONT_AXIS)

cb = fig.colorbar(im, ax=ax, pad=0.02, aspect=26)
cb.set_label(
    "Router flits / epoch  (buffer pressure)", fontsize=11, fontweight="bold"
)
cb.ax.tick_params(labelsize=9)


# mark several instants whose mid-tier hotspot sits on DIFFERENT routers, so
# the moving hotspot is obvious and each instant t is tied to the x-axis.
def hottest_nonsink(j):
    col = M[:, j].copy()
    for r in MC_ROUTERS:
        col[r] = -1
    return int(col.argmax())


# greedily pick 4 well-separated epochs whose hotspots are DISTINCT rows
picks = []
used_rows = set()
for j in range(12, n_ep - 2):
    rr = hottest_nonsink(j)
    if rr not in sel or rr in used_rows:
        continue
    if picks and (j - picks[-1][0]) < 90:  # enforce time spacing
        continue
    picks.append((j, rr))
    used_rows.add(rr)
    if len(picks) == 4:
        break

xtr = ax.get_xaxis_transform()  # x in data, y in axes frac
for k, (j, rr) in enumerate(picks):
    yy = sel.index(rr)
    # vertical time guide across the whole raster
    ax.axvline(j, color="white", ls="--", lw=1.6, alpha=0.9, zorder=4)
    # box the hotspot cell
    ax.add_patch(
        plt.Rectangle(
            (j - 2.0, yy - 0.5),
            4.0,
            1.0,
            fill=False,
            ec="white",
            lw=2.6,
            zorder=6,
        )
    )
    # hotspot label next to the box
    ax.annotate(
        f"hotspot\nR{rr}",
        (j, yy),
        xytext=(j + 22, yy),
        textcoords="data",
        fontsize=9.5,
        color="white",
        fontweight="bold",
        va="center",
        ha="left",
        arrowprops=dict(arrowstyle="->", color="white", lw=1.6),
        bbox=dict(fc="black", ec="white", boxstyle="round,pad=0.22", lw=1.1),
        zorder=7,
    )
    # t-label (with the exact epoch) at the top of the guide -> relatable to x
    ax.text(
        j,
        1.02,
        f"$t_{k+1}$={j}",
        transform=xtr,
        ha="center",
        va="bottom",
        fontsize=12,
        color="black",
        fontweight="bold",
    )

fig.tight_layout()
f_pdf = f"{OUT}/FIG3_hotspot_shift.pdf"
f_png = f"{OUT}/FIG3_hotspot_shift.png"
fig.savefig(f_pdf, bbox_inches="tight")
fig.savefig(f_png, dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"[done] {f_pdf}\n       {f_png}")

# ---------------------------------------------------------------------------
print("\n" + "=" * 72)
print("PAPER TEXT (gem5-measured; SAME run as Fig. 2)")
print("=" * 72)
print(
    f"  Congested routers (buffer pressure >2x epoch mean, >8% of epochs): "
    f"{len(sel)}"
)
print(
    f"  Distinct non-sink routers that act as the top hotspot over the run: "
    f"{len(nonsink_top)}"
)
print(
    "  Marked instants (moving hotspot): "
    + ", ".join(f"t={j}->R{rr}" for j, rr in picks)
)
print()
print("SUGGESTED CAPTION")
print("-" * 72)
print(
    f"Fig. 3. Congestion roams across the mesh within one execution, motivating "
    f"runtime express links. Space-time map of per-router buffer pressure "
    f"(gem5, same constant-load run as Fig. 2: HC 1 GiB/s + LC 2 GiB/s, XY "
    f"routing, 8x8 CustomMesh); each row is a router that becomes congested at "
    f"some point, each column an epoch. Besides the two persistently hot "
    f"memory-controller routers (R21, R42), {len(nonsink_top)} different routers "
    f"take turns as the secondary hotspot: bright cells appear, shift to other "
    f"routers, and fade (marked instants t1..t{len(picks)} sit on routers "
    + ", ".join(f"R{rr}" for _, rr in picks)
    + f"). A link placed at design time to relieve one router therefore sits "
    f"idle whenever the hotspot has moved elsewhere; only express links that are "
    f"activated at runtime can follow the shifting congestion. All values "
    f"measured by gem5."
)
print("=" * 72)

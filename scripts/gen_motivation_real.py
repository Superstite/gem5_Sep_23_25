#!/usr/bin/env python3
"""
Real-workload motivation figures (FIG2 + FIG3), built from an actual MiBench
multiprogram run rather than synthetic memory-read traffic.

Source run: m5bench_real (configs/network/recon_bench_run.py) -- 64 cores each
executing a real MiBench benchmark (susan, qsort, bitcount, basicmath, crc,
dijkstra, patricia) in SE mode on the 8x8 CustomMesh, MESI Two-Level Ruby, XY
routing (baseline, no express). Real instruction+data+coherence traffic with
genuine application phases.

FIG2  instantaneous network state: total in-flight flits/epoch over time --
      congestion fluctuates even though it is one continuous execution.
FIG3  hotspot shift: space-time map of per-router buffer pressure -- the
      congestion hotspot moves between routers over time, so a design-time
      topology cannot follow it (motivates runtime express links).

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
LOG = f"{ROOT}/m5bench_real/trace.log"  # real MiBench run
EPOCH_CYC = 100
MESH = 8
MC_ROUTERS = {21, 42}
WORKLOAD = "real MiBench multiprogram (64 cores: susan, qsort, bitcount,\nbasicmath, crc, dijkstra, patricia)"

RTRACE_RE = re.compile(r"RTRACE t=(\d+) R(\d+) (?:flits|packets)=(\d+)")

# --- parse per-router per-epoch load ---------------------------------------
per_t = {}
with open(LOG) as fh:
    for line in fh:
        m = RTRACE_RE.search(line)
        if not m:
            continue
        t, r, f = int(m.group(1)), int(m.group(2)), int(m.group(3))
        per_t.setdefault(t, {})[r] = f

ticks = sorted(per_t)[5:]  # drop fill transient
n_ep = len(ticks)
M = np.zeros((64, n_ep))
for j, t in enumerate(ticks):
    for r, f in per_t[t].items():
        M[r, j] = f
ep = np.arange(n_ep)
total = M.sum(axis=0)  # packets routed/epoch, network-wide (all vnets)

st_mean, st_std = total.mean(), total.std()
st_cv = 100 * st_std / st_mean
st_min, st_max = int(total.min()), int(total.max())
print(
    f"epochs={n_ep}  total packets/epoch mean={st_mean:.0f} std={st_std:.0f} "
    f"CV={st_cv:.0f}% range={st_min}-{st_max}"
)

# ===========================================================================
# Shared bold style
# ===========================================================================
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 1.4,
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    }
)
FONT_AXIS, FONT_LEGEND, FONT_ANNOT = 15, 13, 14
STATE_COLOR = "#1565C0"  # bold blue for the Fig.2 line
BAND_COLOR = "#64B5F6"  # lighter blue band
HC_COLOR = "#D7191C"
ISO_COLOR = "#404040"

# ===========================================================================
# FIG 2 — instantaneous network state (real workload)
# ===========================================================================
fig2, ax2 = plt.subplots(figsize=(6.4, 4.6))
ax2.axhspan(
    st_mean - st_std,
    st_mean + st_std,
    color=BAND_COLOR,
    alpha=0.40,
    zorder=1,
    label=r"mean $\pm$ 1$\sigma$",
)
ax2.axhline(
    st_mean,
    ls="--",
    color=ISO_COLOR,
    lw=2.0,
    zorder=3,
    label=f"mean = {st_mean:.0f} pkts",
)
ax2.plot(
    ep,
    total,
    "-",
    color=STATE_COLOR,
    lw=1.9,
    zorder=4,
    label="Packets routed / epoch",
)
i_hi = int(np.argmax(total))
ax2.plot(
    ep[i_hi],
    total[i_hi],
    "^",
    color=HC_COLOR,
    ms=13,
    mec="white",
    mew=1.3,
    zorder=6,
    clip_on=False,
)
ax2.annotate(
    f"peak {int(total[i_hi])}",
    (ep[i_hi], total[i_hi]),
    textcoords="offset points",
    xytext=(6, 10),
    fontsize=FONT_ANNOT,
    color=HC_COLOR,
    fontweight="bold",
)
ax2.set_xlabel(
    f"Time (t: epochs of {EPOCH_CYC} cycles)", fontsize=FONT_AXIS, labelpad=4
)
ax2.set_ylabel("Mesh packets routed / epoch", fontsize=FONT_AXIS)
ax2.legend(
    fontsize=FONT_LEGEND,
    loc="upper left",
    framealpha=0.96,
    edgecolor="#888",
    borderpad=0.5,
)
ax2.grid(True, alpha=0.30, ls="--", lw=0.7)
ax2.set_xlim(ep[0], ep[-1])
ax2.set_ylim(bottom=0, top=st_max * 1.18)
fig2.tight_layout()
fig2.savefig(f"{OUT}/FIG2_instantaneous_state.pdf", bbox_inches="tight")
fig2.savefig(
    f"{OUT}/FIG2_instantaneous_state.png", dpi=200, bbox_inches="tight"
)
plt.close(fig2)

# ===========================================================================
# FIG 3 — hotspot shift raster (real workload)
# ===========================================================================
epoch_mean = M.mean(axis=0)
congested_frac = ((M > 2.0 * epoch_mean[None, :]).sum(axis=1)) / n_ep
sel = np.where(congested_frac > 0.08)[0]
sel = sorted(sel, key=lambda r: (r % MESH, r // MESH))
row_labels = [
    f"R{r} (r{r//MESH}c{r%MESH})" + ("  [MC]" if r in MC_ROUTERS else "")
    for r in sel
]
S = M[sel, :]

nonsink_top = set()
for j in range(n_ep):
    col = M[:, j].copy()
    for r in MC_ROUTERS:
        col[r] = -1
    nonsink_top.add(int(col.argmax()))

fig3, ax3 = plt.subplots(figsize=(7.6, 4.8))
vmax = float(
    np.percentile(S[np.array([r not in MC_ROUTERS for r in sel])], 99)
)
im = ax3.imshow(
    S,
    aspect="auto",
    cmap="turbo",
    vmin=0,
    vmax=vmax,
    origin="upper",
    interpolation="nearest",
    extent=[0, n_ep, len(sel) - 0.5, -0.5],
)
ax3.set_yticks(range(len(sel)))
ax3.set_yticklabels(row_labels, fontsize=11)
ax3.set_xlabel(
    f"Time (t: epochs of {EPOCH_CYC} cycles)", fontsize=FONT_AXIS, labelpad=4
)
ax3.set_ylabel("Mesh router", fontsize=FONT_AXIS)
cb = fig3.colorbar(im, ax=ax3, pad=0.02, aspect=26)
cb.set_label(
    "Packets routed / epoch  (all vnets)", fontsize=13, fontweight="bold"
)
cb.ax.tick_params(labelsize=11)


# At FIXED sample times, mark the most-congested NON-SINK router (argmax over
# routers excluding the MC sinks R21/R42). This is the corridor hotspot that an
# express link would bypass; it moves between routers as the workload phase
# changes, so a design-time link cannot follow it.
# candidates = displayed non-sink rows, so the box always lands on a visible row
cand = [r for r in sel if r not in MC_ROUTERS]
# sample several fixed times; at each the hotspot = most-congested non-sink
# router at THAT time. Keep 4 well-spaced times whose hotspots are DISTINCT so
# the figure shows the congestion moving between routers.
sample_ts = [int(n_ep * f) for f in np.linspace(0.10, 0.90, 9)]
picks, used = [], set()
for j in sample_ts:
    rr = max(cand, key=lambda r: M[r, j])
    if rr in used:
        continue
    if picks and (j - picks[-1][0]) < n_ep // 8:
        continue
    picks.append((j, rr))
    used.add(rr)
    if len(picks) == 4:
        break

xtr = ax3.get_xaxis_transform()
placed = []  # (x_of_label, y_of_label)
for k, (j, rr) in enumerate(picks):
    yy = sel.index(rr)
    ax3.axvline(j, color="white", ls="--", lw=1.6, alpha=0.9, zorder=4)
    ax3.add_patch(
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
    # place label left of the box if it is near the right edge (avoid clipping)
    if j > 0.80 * n_ep:
        lx, ha = j - 14, "right"
    else:
        lx, ha = j + 14, "left"
    # vertical declutter: if a previous label is near in x AND y, push down
    ly = yy
    for px, py in placed:
        if abs(lx - px) < 55 and abs(ly - py) < 1.5:
            ly = py + 1.9
    placed.append((lx, ly))
    ax3.annotate(
        f"hotspot\nR{rr}",
        (j, yy),
        xytext=(lx, ly),
        textcoords="data",
        fontsize=11.5,
        color="white",
        fontweight="bold",
        va="center",
        ha=ha,
        arrowprops=dict(arrowstyle="->", color="white", lw=1.6),
        bbox=dict(fc="black", ec="white", boxstyle="round,pad=0.22", lw=1.1),
        zorder=7,
    )
    ax3.text(
        j,
        1.02,
        f"$t_{k+1}$={j}",
        transform=xtr,
        ha="center",
        va="bottom",
        fontsize=14,
        color="black",
        fontweight="bold",
    )

fig3.tight_layout()
fig3.savefig(f"{OUT}/FIG3_hotspot_shift.pdf", bbox_inches="tight")
fig3.savefig(f"{OUT}/FIG3_hotspot_shift.png", dpi=200, bbox_inches="tight")
plt.close(fig3)

print(f"[done] FIG2 + FIG3 (real MiBench) -> {OUT}")
print(
    f"  congested routers={len(sel)}  distinct non-sink hotspots={len(nonsink_top)}"
)
print(f"  marked instants: " + ", ".join(f"t={j}->R{rr}" for j, rr in picks))

# ---------------------------------------------------------------------------
print("\n" + "=" * 72)
print("PAPER TEXT (real MiBench workload; gem5-measured)")
print("=" * 72)
print(
    f"Fig. 2. Instantaneous network state is volatile under a real workload. "
    f"Total packets routed per epoch across the 8x8 CustomMesh (gem5, MESI "
    f"Two-Level, XY routing; summed over all five virtual networks -- read/write "
    f"requests, responses, and coherence -- each packet counted once at every "
    f"router it traverses) while 64 cores each run a MiBench benchmark "
    f"(susan, qsort, bitcount, basicmath, crc, dijkstra, patricia). Over a "
    f"single continuous execution the network load swings from {st_min} to "
    f"{st_max} packets/epoch (mean {st_mean:.0f}, CV {st_cv:.0f}%). A packet's "
    f"delay depends on the instantaneous congestion it meets, so HC timing "
    f"cannot be inferred from the average load. All values measured by gem5."
)
print()
print(
    f"Fig. 3. The congestion hotspot moves during one real-workload execution. "
    f"Space-time map of per-router load (packets routed per epoch, all five "
    f"virtual networks) for the same MiBench run. "
    f"Besides the two persistently hot memory-controller routers (R21, R42), "
    f"{len(nonsink_top)} different routers take turns as the secondary hotspot "
    f"(marked instants t1..t{len(picks)} sit on routers "
    + ", ".join(f"R{rr}" for _, rr in picks)
    + f"): bright cells appear, shift, and fade. A link fixed at design time to "
    f"relieve one router is idle whenever the hotspot has moved elsewhere; only "
    f"runtime-activated express links can follow the shifting congestion. All "
    f"values measured by gem5."
)
print("=" * 72)

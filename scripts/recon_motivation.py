#!/usr/bin/env python3
"""Motivation figures for the runtime-reconfigurable NoC project.

ALL plotted numbers come from real gem5 output. Nothing is synthesised: the
traffic *pattern* is a synthetic mixed-criticality harness (recon_traffic.py),
but every value is measured by gem5 -- either from stats.txt (aggregate packet
latency) or from the per-router, per-epoch ReconTrace debug stream emitted by
GarnetNetwork::reconfigStep() (RTRACE lines).

Three real runs (each doubles as an aggregate scheme AND a time series):
  baseline    : XY, no express links          (routing-algo 1)
  static_all  : all express links always on    (express-active + reconfig, wm=0)
  reconfig    : runtime express reconfiguration (Phase 4 manager)

Figures:
  M1  isolation is pessimistic  -> HC demand at the MC sink is bursty; static
      provisioning must size for the peak, so reserved capacity sits idle.
  M2  congestion is dynamic     -> 8x8 per-router occupancy heatmap at three
      epochs; the hotspot moves in space and time.
  M3  express helps HC / LC pays-> HC latency drops under static_all but LC
      latency rises (permanent cost); reconfig protects LC.
  M4  the sink bottleneck       -> activating express funnels HC into the MC
      router (hc/epoch climbs) while the isolated donor (LC) VC stays idle.
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
OUT = f"{ROOT}/scripts/recon_results/motivation"
os.makedirs(OUT, exist_ok=True)

MESH = 8  # 8x8 CustomMesh
MC_ROUTERS = [21, 42]  # directory-hosting (sink) routers
EPOCH = 1000  # cycles/epoch -> fine time resolution (50 @ 0.05ms)

# Same congested load as recon_eval.py: HC minority driven hard so the shared
# mesh genuinely congests and HC needs relief.
HC_SRCS = "0,3,10,20,29,35,48,59"
LOAD = [
    "--duration",
    "0.05ms",
    "--hc-rate",
    "2GiB/s",
    "--lc-rate",
    "2GiB/s",
    "--high-crit-srcs",
    HC_SRCS,
    "--epoch",
    str(EPOCH),
]

# Each run enables reconfig ONLY so the sampling event fires; the routing algo
# / express flags decide the actual scheme. Baseline (XY) never consults express
# even with the manager on, so its latency is a true baseline.
SCHEMES = {
    "baseline": [
        "--routing-algo",
        "1",
        "--reconfig",
        "1",
        "--high-wm",
        "999999999",
        "--low-wm",
        "0",
    ],
    "static_all": [
        "--routing-algo",
        "2",
        "--express-active",
        "1",
        "--reconfig",
        "1",
        "--high-wm",
        "0",
        "--low-wm",
        "0",
    ],
    "reconfig": [
        "--routing-algo",
        "2",
        "--reconfig",
        "1",
        "--high-wm",
        "200",
        "--low-wm",
        "80",
    ],
}

RTRACE = re.compile(
    r"RTRACE t=(\d+) R(\d+) (?:flits|packets)=(\d+) mc=(\d+) hc=(\d+) lc=(\d+) "
    r"hcocc=(\d+) dnocc=(\d+) ex=(\d+)"
)


def run(name, flags):
    od = f"{ROOT}/m5out_motiv_{name}"
    os.makedirs(od, exist_ok=True)
    log = f"{od}/trace.log"
    print(f"[run] {name} ...", flush=True)
    with open(log, "w") as fh:
        subprocess.run(
            [GEM5, f"--outdir={od}", "--debug-flags=ReconTrace", CFG]
            + LOAD
            + flags,
            stdout=fh,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return od, log


def parse_trace(log):
    """RTRACE lines -> {epoch_tick: {router: (flits, mc, hc, lc)}} sorted."""
    per_t = {}
    with open(log) as fh:
        for line in fh:
            m = RTRACE.search(line)
            if not m:
                continue
            t, r, flits, mc, hc, lc = (int(x) for x in m.groups())
            per_t.setdefault(t, {})[r] = (flits, mc, hc, lc)
    return dict(sorted(per_t.items()))


def stat(txt, key):
    m = re.search(rf"{re.escape(key)}\s+([0-9.]+)", txt)
    return float(m.group(1)) if m else float("nan")


# ---- run the three schemes (real gem5) ------------------------------------
data = {}
for name, flags in SCHEMES.items():
    od, log = run(name, flags)
    trace = parse_trace(log)
    st = open(f"{od}/stats.txt").read()
    data[name] = {
        "trace": trace,
        "hc_lat": stat(st, "network.average_hc_packet_network_latency"),
        "lc_lat": stat(st, "network.average_lc_packet_network_latency"),
    }
    print(
        f"      {name}: {len(trace)} epochs, "
        f"HC_lat={data[name]['hc_lat']:.0f} "
        f"LC_lat={data[name]['lc_lat']:.0f}",
        flush=True,
    )


def mc_series(trace):
    """Per-epoch (epoch_idx, hc, lc) summed over MC routers."""
    xs, hc, lc = [], [], []
    for i, (t, routers) in enumerate(trace.items()):
        h = sum(routers[r][2] for r in MC_ROUTERS if r in routers)
        l = sum(routers[r][3] for r in MC_ROUTERS if r in routers)
        xs.append(i)
        hc.append(h)
        lc.append(l)
    return np.array(xs), np.array(hc), np.array(lc)


# ---- M1: isolation is pessimistic -----------------------------------------
# Measured HC flits/epoch arriving at the MC sink (bursty). Static isolation
# must provision for the worst case (peak, dashed); shaded = reserved-but-idle.
x, hc, _ = mc_series(data["reconfig"]["trace"])
peak = hc.max()
fig, ax = plt.subplots(figsize=(7, 4))
ax.fill_between(
    x, hc, peak, color="#c44e52", alpha=0.18, label="reserved but idle"
)
ax.plot(x, hc, color="#c44e52", lw=1.8, label="measured HC demand")
ax.axhline(
    peak,
    ls="--",
    color="#333",
    lw=1.3,
    label=f"static provision (peak={int(peak)})",
)
ax.set_xlabel(f"epoch ({EPOCH} cycles each)")
ax.set_ylabel("HC flits / epoch at MC sink")
ax.set_title(
    "Static isolation is pessimistic:\nHC demand is bursty, so "
    "peak-sized reservation sits idle most epochs"
)
ax.legend(loc="upper right", fontsize=8)
util = 100.0 * hc.mean() / peak if peak else 0
ax.text(
    0.02,
    0.04,
    f"mean/peak utilisation = {util:.0f}%",
    transform=ax.transAxes,
    fontsize=9,
    bbox=dict(boxstyle="round", fc="white", ec="#999"),
)
fig.tight_layout()
fig.savefig(f"{OUT}/M1_isolation_pessimistic.png", dpi=140)
plt.close(fig)

# ---- M2: congestion is spatially + temporally dynamic ---------------------
# 8x8 per-router flit occupancy at three epochs (early/mid/late) from reconfig.
trace = data["reconfig"]["trace"]
ticks = list(trace.keys())
picks = [
    ticks[len(ticks) // 6],
    ticks[len(ticks) // 2],
    ticks[(5 * len(ticks)) // 6],
]
grids = []
for t in picks:
    g = np.zeros((MESH, MESH))
    for r, (flits, *_) in trace[t].items():
        g[r // MESH, r % MESH] = flits
    grids.append(g)
vmax = max(g.max() for g in grids) or 1
fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))
for ax, g, t in zip(axes, grids, picks):
    im = ax.imshow(g, cmap="magma", vmin=0, vmax=vmax, origin="upper")
    ep = list(trace.keys()).index(t)
    ax.set_title(f"epoch {ep}")
    for r in MC_ROUTERS:
        ax.add_patch(
            plt.Rectangle(
                (r % MESH - 0.5, r // MESH - 0.5),
                1,
                1,
                fill=False,
                ec="cyan",
                lw=2,
            )
        )
    ax.set_xticks(range(MESH))
    ax.set_yticks(range(MESH))
    ax.tick_params(labelsize=7)
fig.suptitle(
    "Congestion is spatially & temporally dynamic: per-router flit "
    "occupancy (cyan = MC sink routers)",
    fontsize=12,
)
fig.colorbar(im, ax=axes, shrink=0.8, label="flits / epoch")
fig.savefig(f"{OUT}/M2_congestion_dynamic.png", dpi=140)
plt.close(fig)

# ---- M3: express helps HC but always-on penalises LC ----------------------
names = ["baseline", "static_all", "reconfig"]
hc_l = [data[n]["hc_lat"] for n in names]
lc_l = [data[n]["lc_lat"] for n in names]
xi = np.arange(len(names))
w = 0.38
fig, ax = plt.subplots(figsize=(7, 4.4))
b1 = ax.bar(xi - w / 2, hc_l, w, label="HC", color="#c44e52")
b2 = ax.bar(xi + w / 2, lc_l, w, label="LC", color="#4c72b0")
ax.bar_label(b1, fmt="%.0f", fontsize=8)
ax.bar_label(b2, fmt="%.0f", fontsize=8)
ax.set_xticks(xi)
ax.set_xticklabels(
    [
        "baseline\n(XY)",
        "static-all\n(always-on express)",
        "reconfig\n(elastic)",
    ]
)
ax.set_ylabel("Avg packet network latency (ticks)")
ax.set_title(
    "Always-on express helps HC but LC pays a permanent cost;\n"
    "elastic reconfig protects LC"
)
ax.legend()
fig.tight_layout()
fig.savefig(f"{OUT}/M3_express_lc_cost.png", dpi=140)
plt.close(fig)

# ---- M4: express funnels HC into the sink (Braess-like relocation) ---------
xb, hcb, lcb = mc_series(data["baseline"]["trace"])
xs, hcs, lcs = mc_series(data["static_all"]["trace"])
fig, ax = plt.subplots(figsize=(7.5, 4.4))
ax.plot(
    xb,
    hcb,
    color="#c44e52",
    ls="--",
    lw=1.6,
    label="HC @ MC, no express (baseline)",
)
ax.plot(xs, hcs, color="#c44e52", lw=2.2, label="HC @ MC, express on (static)")
ax.plot(xs, lcs, color="#4c72b0", lw=1.8, label="donor LC @ MC, express on")
ax.set_xlabel(f"epoch ({EPOCH} cycles each)")
ax.set_ylabel("flits / epoch at MC sink")
ax.set_title(
    "Express relieves the path but funnels HC into the sink:\n"
    "HC demand at MC climbs while the isolated donor (LC) VC stays "
    "idle"
)
ax.legend(loc="upper right", fontsize=8)
fig.tight_layout()
fig.savefig(f"{OUT}/M4_sink_bottleneck.png", dpi=140)
plt.close(fig)

print(f"\n[done] 4 figures -> {OUT}")
for f in sorted(os.listdir(OUT)):
    print("   ", f)

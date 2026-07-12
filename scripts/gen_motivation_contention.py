#!/usr/bin/env python3
"""
Generate IEEE paper motivation figure:
  "Shared NoC Contention Degrades HC Communication Predictability"

Runs real gem5 simulations (8x8 CustomMesh, MESI Two-Level Ruby):
  1. LC-rate sweep (panel a):  HC fixed at 1 GiB/s, LC varies 0.02→3.0 GiB/s
  2. Baseline RTRACE run (panel b): bursty HC 8 GiB/s + steady LC 2 GiB/s,
     XY routing with reconfig enabled (wm=infinity -> never fires express)
     so per-epoch occupancy trace captures the unmitigated baseline.

All data from gem5; nothing is fabricated.

Usage:
    python3 scripts/gen_motivation_contention.py [--skip-runs]
    --skip-runs  : parse existing m5motiv_* dirs instead of re-running gem5
"""

import argparse
import os
import re
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
GEM5 = f"{ROOT}/build/X86_MESI_Two_Level/gem5.debug"
CFG = f"{ROOT}/configs/network/recon_traffic.py"
OUT = f"{ROOT}/scripts/recon_results/motivation"
os.makedirs(OUT, exist_ok=True)

HC_SRCS = "0,3,10,20,29,35,48,59"  # 8 HC sources on 8x8 mesh
MC_ROUTERS = [21, 42]  # directory (sink) router IDs
EPOCH_CYC = 100  # cycles per RTRACE epoch

# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------


def run_gem5(
    outdir,
    extra_flags,
    duration,
    hc_rate,
    lc_rate,
    routing_algo=1,
    hc_srcs=HC_SRCS,
    reconfig=0,
    wm_hi=999999999,
    wm_lo=0,
    bursty=False,
    burst="2000ns",
    gap="3000ns",
    warmup="5000ns",
    epoch=EPOCH_CYC,
    debug_flags="",
):
    """Run gem5 with given params; return outdir path."""
    os.makedirs(outdir, exist_ok=True)
    log = f"{outdir}/run.log"
    cmd = [GEM5, f"--outdir={outdir}"]
    if debug_flags:
        cmd += [f"--debug-flags={debug_flags}"]
    cmd += [
        CFG,
        "--duration",
        duration,
        "--hc-rate",
        hc_rate,
        "--lc-rate",
        lc_rate,
        "--high-crit-srcs",
        hc_srcs,
        "--routing-algo",
        str(routing_algo),
        "--reconfig",
        str(reconfig),
        "--high-wm",
        str(wm_hi),
        "--low-wm",
        str(wm_lo),
        "--epoch",
        str(epoch),
    ]
    if bursty:
        cmd += ["--hc-burst", burst, "--hc-gap", gap, "--hc-warmup", warmup]
    cmd += extra_flags
    print(f"  [gem5] {outdir} ... ", end="", flush=True)
    with open(log, "w") as fh:
        ret = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    if ret.returncode != 0:
        print("FAILED")
    else:
        print("ok")
    return outdir


def stat(stats_txt, key):
    m = re.search(rf"{re.escape(key)}\s+([0-9.]+)", stats_txt)
    return float(m.group(1)) if m else float("nan")


RTRACE_RE = re.compile(
    r"RTRACE t=(\d+) R(\d+) (?:flits|packets)=(\d+) mc=(\d+) hc=(\d+) lc=(\d+) "
    r"hcocc=(\d+) dnocc=(\d+) ex=(\d+)"
)


def parse_rtrace(log_path):
    """Return per-epoch dict {tick: {router: namedtuple fields}}."""
    per_t = {}
    with open(log_path) as fh:
        for line in fh:
            m = RTRACE_RE.search(line)
            if not m:
                continue
            t, r, flits, mc, hc, lc, hcocc, dnocc, ex = map(int, m.groups())
            per_t.setdefault(t, {})[r] = dict(
                flits=flits,
                mc=mc,
                hc=hc,
                lc=lc,
                hcocc=hcocc,
                dnocc=dnocc,
                ex=ex,
            )
    return dict(sorted(per_t.items()))


def mc_series_from_trace(trace):
    """Sum HC, LC, hcocc, dnocc over MC routers per epoch."""
    ticks, hc_arr, lc_arr, hcocc_arr, dnocc_arr, ex_arr = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    for t, routers in trace.items():
        ticks.append(t)
        hc_arr.append(sum(routers.get(r, {}).get("hc", 0) for r in MC_ROUTERS))
        lc_arr.append(sum(routers.get(r, {}).get("lc", 0) for r in MC_ROUTERS))
        hcocc_arr.append(
            sum(routers.get(r, {}).get("hcocc", 0) for r in MC_ROUTERS)
        )
        dnocc_arr.append(
            sum(routers.get(r, {}).get("dnocc", 0) for r in MC_ROUTERS)
        )
        ex_arr.append(max(routers.get(r, {}).get("ex", 0) for r in MC_ROUTERS))
    return (
        np.array(ticks),
        np.array(hc_arr),
        np.array(lc_arr),
        np.array(hcocc_arr),
        np.array(dnocc_arr),
        np.array(ex_arr),
    )


def all_router_occ(trace):
    """Return per-epoch 8x8 grid of total flit counts (for heatmap)."""
    epochs = list(trace.keys())
    grids = []
    for t in epochs:
        g = np.zeros((8, 8))
        for r, d in trace[t].items():
            g[r // 8, r % 8] = d["flits"]
        grids.append(g)
    return epochs, grids


# ---------------------------------------------------------------------------
# Run simulations
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser()
parser.add_argument(
    "--skip-runs",
    action="store_true",
    help="Use existing m5motiv_* dirs; skip gem5 invocations.",
)
args = parser.parse_args()

# --- Panel (a): LC-rate sweep (steady HC, baseline XY routing) ---
LC_RATES = [0.02, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]  # GiB/s per core
SWEEP_DIRS = [f"{ROOT}/m5motiv_lc{str(r).replace('.','p')}" for r in LC_RATES]

print("\n=== Panel (a): LC rate sweep ===")
for lc_r, od in zip(LC_RATES, SWEEP_DIRS):
    if not args.skip_runs or not os.path.isfile(f"{od}/stats.txt"):
        run_gem5(
            od,
            [],
            duration="0.04ms",
            hc_rate="1GiB/s",
            lc_rate=f"{lc_r}GiB/s",
            routing_algo=1,
            reconfig=0,
        )
    else:
        print(f"  [skip] {od}")

sweep = []
for lc_r, od in zip(LC_RATES, SWEEP_DIRS):
    st = open(f"{od}/stats.txt").read()
    hc_lat = stat(st, "network.average_hc_packet_network_latency")
    lc_lat = stat(st, "network.average_lc_packet_network_latency")
    sweep.append((lc_r, hc_lat, lc_lat))
    print(
        f"  LC={lc_r:4.2f} GiB/s  HC_lat={hc_lat:8.0f}  LC_lat={lc_lat:8.0f}"
    )

# --- Panel (b): Baseline RTRACE (bursty HC, no express) ---
RTRACE_DIR = f"{ROOT}/m5motiv_rtrace_base"
print("\n=== Panel (b): Baseline RTRACE run ===")
if not args.skip_runs or not os.path.isfile(f"{RTRACE_DIR}/run.log"):
    run_gem5(
        RTRACE_DIR,
        [],
        duration="0.05ms",
        hc_rate="8GiB/s",
        lc_rate="2GiB/s",
        routing_algo=1,  # XY baseline, no express links
        reconfig=1,  # enable reconfigStep (for RTRACE output)
        wm_hi=999999999,  # watermark so high it never fires
        wm_lo=0,
        bursty=True,
        burst="2000ns",
        gap="3000ns",
        warmup="5000ns",
        epoch=EPOCH_CYC,
        debug_flags="ReconTrace",
    )
else:
    print(f"  [skip] {RTRACE_DIR}")

trace = parse_rtrace(f"{RTRACE_DIR}/run.log")
ticks, mc_hc, mc_lc, mc_hcocc, mc_dnocc, _ = mc_series_from_trace(trace)
epoch_idx = np.arange(len(ticks))

print(
    f"  Parsed {len(ticks)} epochs from RTRACE ({len(ticks)*EPOCH_CYC} cycles)"
)
print(f"  HC at MC: mean={mc_hc.mean():.1f} peak={mc_hc.max()}")
print(f"  LC at MC: mean={mc_lc.mean():.1f} peak={mc_lc.max()}")
print(f"  HC occ  : mean={mc_hcocc.mean():.1f} peak={mc_hcocc.max()}")

# --- Steady (non-bursty) RTRACE run: constant offered load, XY baseline ---
# Used for Fig. 2: shows that even at CONSTANT injection the instantaneous
# network state (total in-flight flits / epoch) swings widely -> a packet's
# delay depends on when it enters, i.e. timing is state-dependent.
STEADY_DIR = f"{ROOT}/m5motiv_rtrace_steady"
print("\n=== Fig 2: Steady-load RTRACE run ===")
if not args.skip_runs or not os.path.isfile(f"{STEADY_DIR}/run.log"):
    run_gem5(
        STEADY_DIR,
        [],
        duration="0.05ms",
        hc_rate="1GiB/s",
        lc_rate="2GiB/s",
        routing_algo=1,  # XY baseline, no express
        reconfig=1,
        wm_hi=999999999,
        wm_lo=0,  # RTRACE only, never fires
        bursty=False,  # constant offered load
        epoch=EPOCH_CYC,
        debug_flags="ReconTrace",
    )
else:
    print(f"  [skip] {STEADY_DIR}")

steady_trace = parse_rtrace(f"{STEADY_DIR}/run.log")


def total_flits_series(tr):
    """Per-epoch total in-flight flits summed over all 64 routers."""
    xs, tot = [], []
    for i, (t, routers) in enumerate(sorted(tr.items())):
        xs.append(i)
        tot.append(sum(d["flits"] for d in routers.values()))
    return np.array(xs), np.array(tot)


st_epoch, st_total = total_flits_series(steady_trace)
# Drop first few epochs (fill transient) so we measure steady-state volatility
WARM_DROP = 5
st_epoch = st_epoch[WARM_DROP:]
st_total = st_total[WARM_DROP:]
st_mean = st_total.mean()
st_std = st_total.std()
st_cv = 100.0 * st_std / st_mean if st_mean else 0.0
st_min, st_max = st_total.min(), st_total.max()
print(
    f"  Steady total flits/epoch: mean={st_mean:.0f} std={st_std:.0f} "
    f"CV={st_cv:.0f}%  range=[{st_min},{st_max}]  (x{st_max/max(st_min,1):.1f})"
)

# ---------------------------------------------------------------------------
# Compute derived quantities
# ---------------------------------------------------------------------------
lc_total_bw = np.array(
    [r[0] * 56 for r in sweep]
)  # 56 LC cores × per-core rate
hc_lats = np.array([r[1] for r in sweep])
lc_lats = np.array([r[2] for r in sweep])
isolation_lat = hc_lats[0]  # near-isolation (LC≈0) HC latency
peak_lc_lat = hc_lats[-1]  # HC latency at max LC load
deg_pct = 100.0 * (peak_lc_lat - isolation_lat) / isolation_lat

# Bursty epoch parameters (in epochs of EPOCH_CYC cycles):
#   warmup  = 5000 cycles = 50 epochs
#   burst   = 2000 cycles = 20 epochs
#   gap     = 3000 cycles = 30 epochs
WARMUP_EP = 5000 // EPOCH_CYC  # 50
BURST_EP = 2000 // EPOCH_CYC  # 20
GAP_EP = 3000 // EPOCH_CYC  # 30

# Burst windows as epoch indices
burst_windows = []
start = WARMUP_EP
while start < len(epoch_idx):
    end = min(start + BURST_EP, len(epoch_idx))
    burst_windows.append((start, end))
    start = end + GAP_EP

# ---------------------------------------------------------------------------
# FIGURES  (two independent, standalone IEEE-column PDFs)
# ---------------------------------------------------------------------------
# BOLD, saturated palette
HC_COLOR = "#D7191C"  # bold red   (HC / interference)
LC_COLOR = "#2C7BB6"  # bold blue  (LC)
ISO_COLOR = "#404040"  # dark grey  (isolation baseline)
STATE_COLOR = "#6A1B9A"  # bold purple (instantaneous network state)
BAND_COLOR = "#AB47BC"  # lighter purple band

FONT_AXIS = 15
FONT_TITLE = 15
FONT_LEGEND = 13
FONT_ANNOT = 14

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",  # all text bold (ticks, legend, labels)
        "axes.labelweight": "bold",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 1.4,
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    }
)

# ===========================================================================
# FIGURE 1 — Interference exists and it is bad.
#   HC latency grows monotonically with LC cross-traffic, HC rate fixed.
# ===========================================================================
fig1, ax1 = plt.subplots(figsize=(6.4, 4.6))

# gem5 Ruby latency stats are in TICKS; clock=1000 ticks/cycle (1 GHz) -> cycles.
TICKS_PER_CYCLE = 1000
hc_cyc = hc_lats / TICKS_PER_CYCLE  # HC avg latency in cycles
iso_cyc = isolation_lat / TICKS_PER_CYCLE  # HC-almost-alone latency in cycles
peak_cyc = peak_lc_lat / TICKS_PER_CYCLE

# shaded interference penalty (baseline -> actual)
ax1.fill_between(
    lc_total_bw,
    iso_cyc,
    hc_cyc,
    color=HC_COLOR,
    alpha=0.16,
    zorder=2,
    label="interference penalty",
)

# baseline reference: HC near isolation (lowest LC load in the sweep)
ax1.axhline(
    iso_cyc,
    ls=(0, (6, 4)),
    color=ISO_COLOR,
    lw=2.0,
    zorder=3,
    label=f"HC near isolation (LC≈{lc_total_bw[0]:.0f} GiB/s): "
    f"{iso_cyc:.0f} cycles",
)

# main HC latency curve — bold
ax1.plot(
    lc_total_bw,
    hc_cyc,
    "o-",
    color=HC_COLOR,
    lw=3.6,
    ms=12,
    mec="white",
    mew=2.2,
    zorder=5,
    clip_on=False,
    label="HC latency (HC rate FIXED @ 1 GiB/s/core)",
)

# +XX% callout near the peak
ax1.annotate(
    f"+{deg_pct:.0f}%\nHC latency",
    xy=(lc_total_bw[-1], hc_cyc[-1]),
    xytext=(lc_total_bw[-3] * 0.98, (iso_cyc + hc_cyc[-2]) / 2),
    fontsize=FONT_ANNOT + 1,
    color=HC_COLOR,
    fontweight="bold",
    ha="center",
    va="center",
    arrowprops=dict(
        arrowstyle="-|>",
        color=HC_COLOR,
        lw=2.0,
        connectionstyle="arc3,rad=0.18",
    ),
    bbox=dict(fc="white", ec=HC_COLOR, boxstyle="round,pad=0.35", lw=1.6),
)

ax1.set_xlabel(
    "Total LC cross-traffic injected (GiB/s)", fontsize=FONT_AXIS, labelpad=4
)
ax1.set_ylabel("HC avg packet latency (cycles)", fontsize=FONT_AXIS)
ax1.legend(
    fontsize=FONT_LEGEND,
    loc="upper left",
    framealpha=0.96,
    edgecolor="#888",
    borderpad=0.6,
)
ax1.grid(True, alpha=0.30, ls="--", lw=0.7)
ax1.set_xlim(left=-3, right=lc_total_bw[-1] * 1.04)
ax1.set_ylim(bottom=iso_cyc * 0.90, top=hc_cyc[-1] * 1.12)

fig1.tight_layout()
f1_pdf = f"{OUT}/FIG1_interference.pdf"
f1_png = f"{OUT}/FIG1_interference.png"
fig1.savefig(f1_pdf, bbox_inches="tight")
fig1.savefig(f1_png, dpi=200, bbox_inches="tight")
plt.close(fig1)

# ===========================================================================
# FIGURE 2 — Because interference varies, communication timing depends on the
#   INSTANTANEOUS network state.  Constant offered load, yet total in-flight
#   flits swing widely epoch-to-epoch -> a packet's delay depends on WHEN it
#   enters the network.
# ===========================================================================
fig2, ax2 = plt.subplots(figsize=(6.4, 4.6))

# mean +/- 1 std band
ax2.axhspan(
    st_mean - st_std,
    st_mean + st_std,
    color=BAND_COLOR,
    alpha=0.18,
    zorder=1,
    label=r"mean $\pm$ 1$\sigma$",
)
ax2.axhline(
    st_mean,
    ls="--",
    color=ISO_COLOR,
    lw=2.0,
    zorder=3,
    label=f"mean = {st_mean:.0f} flits",
)

# instantaneous congestion time series — bold
ax2.plot(
    st_epoch,
    st_total,
    "-",
    color=STATE_COLOR,
    lw=1.9,
    zorder=4,
    label="In-flight flits / epoch",
)

# highlight peak to dramatise variability
i_hi = int(np.argmax(st_total))
ax2.plot(
    st_epoch[i_hi],
    st_total[i_hi],
    "^",
    color=HC_COLOR,
    ms=13,
    mec="white",
    mew=1.3,
    zorder=6,
    clip_on=False,
)
ax2.annotate(
    f"peak {st_total[i_hi]}",
    (st_epoch[i_hi], st_total[i_hi]),
    textcoords="offset points",
    xytext=(6, 10),
    fontsize=FONT_ANNOT,
    color=HC_COLOR,
    fontweight="bold",
)

ax2.set_xlabel(
    f"Time (epoch = {EPOCH_CYC} cycles)", fontsize=FONT_AXIS, labelpad=4
)
ax2.set_ylabel("Mesh In-flight flits / epoch", fontsize=FONT_AXIS)
ax2.legend(
    fontsize=FONT_LEGEND,
    loc="upper left",
    framealpha=0.96,
    edgecolor="#888",
    borderpad=0.6,
    ncol=1,
)
ax2.grid(True, alpha=0.30, ls="--", lw=0.7)
ax2.set_ylim(bottom=0, top=st_max * 1.18)

fig2.tight_layout()
f2_pdf = f"{OUT}/FIG2_instantaneous_state.pdf"
f2_png = f"{OUT}/FIG2_instantaneous_state.png"
fig2.savefig(f2_pdf, bbox_inches="tight")
fig2.savefig(f2_png, dpi=200, bbox_inches="tight")
plt.close(fig2)

print(f"\n[done] wrote 2 standalone figures ->")
for f in (f1_pdf, f1_png, f2_pdf, f2_png):
    print("   ", f)

# ---------------------------------------------------------------------------
# Print paper-ready text (all values from gem5)
# ---------------------------------------------------------------------------
print("\n" + "=" * 72)
print("PAPER TEXT  (every value measured by gem5; nothing fabricated)")
print("=" * 72)
print("\nFIG. 1  — Interference exists and is harmful")
print(f"  (gem5 latency stats are in TICKS; clock=1000 ticks/cycle @1GHz)")
print(
    f"  HC near isolation (LC≈{lc_total_bw[0]:.0f} GiB/s): "
    f"{isolation_lat:.0f} ticks = {iso_cyc:.0f} cycles"
)
print(
    f"  HC latency at heavy LC ({lc_total_bw[-1]:.0f} GiB/s): "
    f"{peak_lc_lat:.0f} ticks = {peak_cyc:.0f} cycles"
)
print(
    f"  => HC latency inflation from LC contention: +{deg_pct:.0f}% "
    f"(HC injection held fixed at 1 GiB/s/core)"
)
print("\nFIG. 2  — Timing depends on the instantaneous network state")
print(f"  Constant offered load (HC 1 GiB/s + LC 2 GiB/s, non-bursty, XY)")
print(
    f"  Mesh in-flight flits/epoch: mean={st_mean:.0f}, std={st_std:.0f}, "
    f"min={st_min}, max={st_max}"
)
print(
    f"  => coefficient of variation CV={st_cv:.0f}%, "
    f"instantaneous range {st_min}-{st_max} flits/epoch"
)

print("\n" + "-" * 72)
print("SUGGESTED CAPTIONS")
print("-" * 72)
print(
    f"Fig. 1. Shared-NoC interference is real and harmful. Average HC packet "
    f"network latency (gem5, 8x8 CustomMesh, MESI Two-Level, XY routing) grows "
    f"monotonically from {iso_cyc:.0f} to {peak_cyc:.0f} cycles "
    f"(+{deg_pct:.0f}%) as low-criticality (LC) cross-traffic rises from the "
    f"lightest sweep point ({lc_total_bw[0]:.0f} GiB/s, where HC runs almost "
    f"alone) to {lc_total_bw[-1]:.0f} GiB/s, even though the HC injection rate "
    f"is held FIXED at 1 GiB/s per core. HC communication latency is therefore "
    f"not a property of the HC flow itself but of the contention it meets in "
    f"the shared fabric."
)
print()
print(
    f"Fig. 2. HC communication predictability depends on the instantaneous "
    f"network state. Under a CONSTANT offered load (HC 1 GiB/s + LC 2 GiB/s, "
    f"XY routing), the total number of in-flight flits in the mesh still "
    f"fluctuates from {st_min} to {st_max} per epoch (coefficient of variation "
    f"{st_cv:.0f}%). Because the congestion "
    f"a packet encounters changes from moment to moment, two identical HC "
    f"requests injected at different instants experience different delays, so "
    f"worst-case timing cannot be inferred from the average load alone. "
    f"All values are measured directly by gem5; none are fabricated."
)
print("=" * 72)

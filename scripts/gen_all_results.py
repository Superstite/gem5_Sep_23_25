#!/usr/bin/env python3
"""Consolidated result figures — reads existing m5out dirs (real gem5), no re-run.
Produces: F1 congestion-collapse (activation delay), F2 HC-saturation sweep,
F3 elastic HC-vs-duty (bursty), F4 HC-vs-duty Pareto (sparse: all controllers).
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/summary"
os.makedirs(OUT, exist_ok=True)
RED, BLU, GRY, GRN, PUR, ORG = (
    "#c44e52",
    "#4c72b0",
    "#777",
    "#55a868",
    "#8172b3",
    "#dd8452",
)


def hc(d):
    p = f"{ROOT}/{d}/stats.txt"
    if not os.path.exists(p):
        return None
    m = re.search(
        r"average_hc_packet_network_latency\s+([0-9.]+)", open(p).read()
    )
    return float(m.group(1)) if m else None


def duty(d):
    for fn in ("run.log", "trace.log"):
        p = f"{ROOT}/{d}/{fn}"
        if os.path.exists(p):
            on = tot = 0
            for ln in open(p):
                if "RTRACE" in ln:
                    tot += 1
                    if "ex=1" in ln:
                        on += 1
            return 100.0 * on / tot if tot else None
    return None


# ---- F1: congestion collapse — HC vs activation delay (epoch) ----
delays = [
    ("m5out_ep20", 20),
    ("m5out_ep100", 100),
    ("m5out_ep500", 500),
    ("m5out_D_rtOnAll", 1000),
]
xs = [e for _, e in delays]
ys = [hc(d) for d, _ in delays]
fig, ax = plt.subplots(figsize=(6.8, 4.4))
ax.plot(xs, ys, "o-", color=RED, lw=2, label="runtime activate-all")
ax.axhline(
    hc("m5out_C_initOn"), ls="--", color=GRN, label="express active at init"
)
ax.axhline(26165, ls=":", color="#333", label="static-all (ceiling)")
ax.axhline(47681, ls=":", color=GRY, label="baseline (no express)")
ax.set_xscale("log")
ax.set_xlabel("activation delay = decision epoch (cycles)")
ax.set_ylabel("Avg HC packet network latency (ticks)")
ax.set_title(
    "Congestion collapse: late runtime activation loses the benefit\n"
    "(W2, HC 2 GiB/s sustained)"
)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(f"{OUT}/F1_collapse.png", dpi=140)
plt.close(fig)

# ---- F2: HC saturation sweep ----
rates = [2, 4, 8, 16]
series = {"baseline": GRY, "static_all": RED, "reconfig": BLU}
fig, ax = plt.subplots(figsize=(6.8, 4.4))
for s, c in series.items():
    y = [hc(f"m5out_sweep_{s}_{r}GiBs") for r in rates]
    ax.plot(
        rates,
        y,
        "o-",
        color=c,
        lw=2,
        label=s.replace("_", "-").replace("all", "all express"),
    )
ax.set_xscale("log", base=2)
ax.set_xticks(rates)
ax.set_xticklabels(rates)
ax.set_xlabel("HC injection rate (GiB/s)")
ax.set_ylabel("Avg HC packet network latency (ticks)")
ax.set_title(
    "HC latency vs HC load: runtime manager tracks baseline\n"
    "(more HC does not help it) — W2"
)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(f"{OUT}/F2_saturation.png", dpi=140)
plt.close(fig)

# ---- F3: elastic bursty — HC bars + duty line (W3) ----
els = [
    ("baseline", "m5out_pred_baseline"),
    ("static-all", "m5out_pred_static_all"),
    ("reactive\nglobal", "m5out_pred_reactive_global"),
    ("MFDFA\npredictive", "m5out_pred_predictive"),
]
names = [n for n, _ in els]
hcv = [hc(d) for _, d in els]
dtv = [duty(d) for _, d in els]
x = np.arange(len(names))
fig, ax = plt.subplots(figsize=(7, 4.6))
bars = ax.bar(x, hcv, 0.55, color=RED)
ax.bar_label(bars, fmt="%.0f", fontsize=8)
ax.set_ylabel("Avg HC packet network latency (ticks)", color=RED)
ax.set_xticks(x)
ax.set_xticklabels(names)
ax2 = ax.twinx()
ax2.plot(x, dtv, "D-", color="#222", label="express duty")
ax2.set_ylabel("express duty cycle (%)")
ax2.set_ylim(0, 105)
for i, d in enumerate(dtv):
    if d is not None:
        ax2.annotate(
            f"{d:.0f}%",
            (i, d),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8,
        )
ax.set_title(
    "Elastic reactive express ≈ static HC at <½ duty; predictor adds "
    "duty, no gain (W3)"
)
fig.tight_layout()
fig.savefig(f"{OUT}/F3_elastic_duty.png", dpi=140)
plt.close(fig)

# ---- F4: sparse Pareto — HC vs duty, all controllers (W4) ----
pts = [
    ("baseline", "m5out_rl_baseline", "s", GRY),
    ("static-all", "m5out_rl_static", "*", RED),
    ("reactive (feedback)", "m5out_rl_reactive", "o", BLU),
    ("MFDFA-predictive", "m5out_rl_mfdfa", "^", GRN),
    ("RL λ=0.1", "m5out_rl_deploy_lam0.1", "D", PUR),
    ("RL λ=0.6", "m5out_rl_deploy_lam0.6", "D", PUR),
    ("oracle lead0", "m5o_lead0", "P", ORG),
    ("oracle lead2µs", "m5o_lead2000", "P", ORG),
    ("oracle tail on5µs", "m5t_on5", "X", "#937860"),
]
fig, ax = plt.subplots(figsize=(8.2, 5.2))
for lab, d, mk, c in pts:
    h, dt = hc(d), duty(d)
    if h is None or dt is None:
        continue
    ax.scatter(
        dt,
        h,
        s=110,
        marker=mk,
        color=c,
        edgecolor="k" if "reactive" in lab else "none",
        linewidth=1.2,
        zorder=3,
        label=lab,
    )
ax.axhline(27360, ls=":", color=RED, lw=1)
ax.annotate(
    "static HC ceiling", (1, 27360), fontsize=8, color=RED, va="bottom"
)
ax.set_xlabel("express duty cycle (%)  — lower = cheaper")
ax.set_ylabel("Avg HC packet network latency (ticks)  — lower = better")
ax.set_title(
    "Reactive feedback dominates every predictive/RL/oracle point (W4)\n"
    "=> prediction has no headroom; MFDFA is not the root cause"
)
ax.legend(fontsize=7, ncol=2)
fig.tight_layout()
fig.savefig(f"{OUT}/F4_pareto.png", dpi=140)
plt.close(fig)

print(f"[done] -> {OUT}")
for f in sorted(os.listdir(OUT)):
    print("   ", f)

#!/usr/bin/env python3
"""Two result plots (real gem5): baseline vs express-link activation,
(a) with VC merging DISABLED and (b) with VC merging ENABLED, so the express
gain and the added VC-merge gain at influential routers are both visible.

Workload chosen so the two-factor merge gate can actually open: HC bursts
(saturate HC's VC subset at the influential routers 21/42) while LC is light
(donor VC subset genuinely idle). All latencies from stats.txt.
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
OUT = f"{ROOT}/scripts/recon_results/merge"
os.makedirs(OUT, exist_ok=True)

LOAD = [
    "--duration",
    "0.1ms",
    "--hc-rate",
    "8GiB/s",
    "--lc-rate",
    "0.2GiB/s",
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
]
EXPRESS = [
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
]
BASELINE = ["--routing-algo", "1"]
MERGE = ["--mc-merge", "1", "--mc-hc-hi", "10", "--mc-lc-lo", "20"]

CONFIGS = {
    # (merge_off) baseline vs express
    "off_base": BASELINE,
    "off_expr": EXPRESS,
    # (merge_on) baseline vs express, VC merging enabled at influential routers
    "on_base": BASELINE + MERGE,
    "on_expr": EXPRESS + MERGE,
}


def run(name, flags):
    od = f"{ROOT}/m5out_merge_{name}"
    os.makedirs(od, exist_ok=True)
    dbg = "--debug-flags=RubyNetwork" if "on_" in name else None
    cmd = (
        [GEM5, f"--outdir={od}"]
        + ([dbg] if dbg else [])
        + [CFG]
        + LOAD
        + flags
    )
    print(f"[run] {name}", flush=True)
    with open(f"{od}/run.log", "w") as fh:
        subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, check=False)
    st = open(f"{od}/stats.txt").read()

    def g(k):
        m = re.search(rf"{re.escape(k)}\s+([0-9.]+)", st)
        return float(m.group(1)) if m else float("nan")

    arms = (
        len(re.findall(r"RECONF_MERGE.*ARM", open(f"{od}/run.log").read()))
        if dbg
        else 0
    )
    return dict(
        hc=g("network.average_hc_packet_network_latency"),
        lc=g("network.average_lc_packet_network_latency"),
        arms=arms,
    )


res = {k: run(k, f) for k, f in CONFIGS.items()}
for k, v in res.items():
    print(f"  {k:9s} HC={v['hc']:.0f} LC={v['lc']:.0f} merge_arms={v['arms']}")


def panel(ax, base, expr, title):
    x = np.arange(2)
    w = 0.36
    hc = [res[base]["hc"], res[expr]["hc"]]
    lc = [res[base]["lc"], res[expr]["lc"]]
    b1 = ax.bar(x - w / 2, hc, w, label="HC", color="#c44e52")
    b2 = ax.bar(x + w / 2, lc, w, label="LC", color="#4c72b0")
    ax.bar_label(b1, fmt="%.0f", fontsize=8)
    ax.bar_label(b2, fmt="%.0f", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(["baseline\n(XY, no express)", "express\nactivation"])
    ax.set_ylabel("Avg packet network latency (ticks)")
    ax.set_title(title)
    ax.legend()
    d = 100 * (1 - res[expr]["hc"] / res[base]["hc"])
    ax.annotate(
        f"HC {d:+.1f}%",
        (1, res[expr]["hc"]),
        textcoords="offset points",
        xytext=(0, 14),
        ha="center",
        fontsize=9,
        color="#c44e52",
    )


ymax = max(res[k]["hc"] for k in res) * 1.12
for tag, (b, e, ttl) in {
    "A_merge_off": (
        "off_base",
        "off_expr",
        "VC merging DISABLED: express activation vs baseline",
    ),
    "B_merge_on": (
        "on_base",
        "on_expr",
        f"VC merging ENABLED: express + merge vs baseline "
        f"(merge armed {res['on_expr']['arms']}x)",
    ),
}.items():
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    panel(ax, b, e, ttl)
    ax.set_ylim(0, ymax)
    fig.tight_layout()
    fig.savefig(f"{OUT}/{tag}.png", dpi=140)
    plt.close(fig)

# combined 4-bar HC-only view to see both effects at once
fig, ax = plt.subplots(figsize=(7.2, 4.6))
order = ["off_base", "off_expr", "on_base", "on_expr"]
labels = [
    "baseline",
    "express\n(merge off)",
    "baseline\n(merge on)",
    "express+merge",
]
hc = [res[k]["hc"] for k in order]
bars = ax.bar(range(4), hc, color=["#777", "#c44e52", "#999", "#8c2d2d"])
ax.bar_label(bars, fmt="%.0f", fontsize=9)
ax.set_xticks(range(4))
ax.set_xticklabels(labels)
ax.set_ylabel("Avg HC packet network latency (ticks)")
ax.set_title("HC latency: express activation and VC merging")
fig.tight_layout()
fig.savefig(f"{OUT}/C_combined_hc.png", dpi=140)
plt.close(fig)

print(f"\n[done] -> {OUT}")

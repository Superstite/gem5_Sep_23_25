#!/usr/bin/env python3
"""Reactive vs predictive controllers on the REAL MiBench workload (new VC
layout): reactive (Policy 1, feedback) vs MFDFA-style predictive (Policy 2) vs
RL Q-learning (Policy 3, trained then frozen). HC packet latency. Real gem5.
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
CFG = f"{ROOT}/configs/network/recon_bench_run.py"
OUT = f"{ROOT}/scripts/recon_results/rl"
# Q-table written by the training run, reloaded frozen by the deploy run.
QF = os.environ.get("RECON_Q_FILE", f"{OUT}/q_real.txt")
os.makedirs(OUT, exist_ok=True)
T = ["--routing-algo", "2", "--max-ticks", "25000000"]
HC = ["--hc-hi", "24", "--hc-lo", "10"]


def run(name, flags):
    od = f"{ROOT}/m5rl_{name}"
    os.makedirs(od, exist_ok=True)
    if (
        not os.path.exists(f"{od}/stats.txt")
        or os.path.getsize(f"{od}/stats.txt") == 0
    ):
        print(f"[run] {name}", flush=True)
        with open(f"{od}/run.log", "w") as fh:
            subprocess.run(
                [GEM5, f"--outdir={od}", CFG] + T + flags,
                stdout=fh,
                stderr=subprocess.STDOUT,
                check=False,
            )
    m = re.search(
        r"average_hc_packet_network_latency\s+([0-9.]+)",
        open(f"{od}/stats.txt").read(),
    )
    return float(m.group(1)) / 1000.0  # cycles


reactive = run("reactive", ["--reconfig-policy", "1"] + HC)
predictive = run(
    "predictive",
    [
        "--reconfig-policy",
        "2",
        "--slope-hi",
        "15",
        "--hold-epochs",
        "4",
        "--ewma-alpha",
        "0.4",
    ]
    + HC,
)
# RL: train (dump Q) then deploy frozen
run(
    "rl_train",
    [
        "--reconfig-policy",
        "3",
        "--rl-train",
        "1",
        "--q-file",
        QF,
        "--rl-lambda",
        "0.3",
        "--rl-occ-scale",
        "15",
        "--ewma-alpha",
        "0.4",
    ]
    + HC,
)
rl = run(
    "rl_deploy",
    [
        "--reconfig-policy",
        "3",
        "--rl-train",
        "0",
        "--q-file",
        QF,
        "--rl-lambda",
        "0.3",
        "--rl-occ-scale",
        "15",
        "--ewma-alpha",
        "0.4",
    ]
    + HC,
)

names = ["Reactive\n(feedback)", "Predictive\n(MFDFA)", "RL\n(Q-learning)"]
hc = [reactive, predictive, rl]
print(
    "HC (cyc):",
    {n.replace(chr(10), " "): f"{v:.1f}" for n, v in zip(names, hc)},
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
fig, ax = plt.subplots(figsize=(7.0, 5.0))
# bold colors from the energy figure: blue, rust, green
cols = ["#1a53ff", "#B7410E", "#2ca02c"]
bars = ax.bar(
    range(3),
    hc,
    0.6,
    color=cols,
    edgecolor="black",
    linewidth=1.2,
    hatch=["//", "\\\\", "---"],
)
ax.bar_label(bars, fmt="%.1f", fontsize=14, fontweight="bold")
for i in (1, 2):
    ax.annotate(
        f"{100*(hc[i]/hc[0]-1):+.1f}%\nvs. reactive",
        (i, hc[i]),
        textcoords="offset points",
        xytext=(0, 18),
        ha="center",
        fontsize=12,
        fontweight="bold",
        color="#333",
    )
ax.set_xticks(range(3))
ax.set_xticklabels(names)
ax.set_ylim(0, max(hc) * 1.25)
ax.set_ylabel("Avg HC packet network latency\n(Cycles)", fontsize=15)
for lb in ax.get_xticklabels() + ax.get_yticklabels():
    lb.set_fontweight("bold")
fig.tight_layout()
fig.savefig(f"{OUT}/F17_rl_real.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F17_rl_real.pdf")

#!/usr/bin/env python3
"""Verdict figure: is prediction useful for elastic express activation, and is
MFDFA the reason predictive lost? Reads REAL gem5 runs already on disk (no
re-run) and plots the HC-latency vs express-duty Pareto for every controller:
baseline, static-all, reactive(feedback), MFDFA-predictive, RL(Q-learning), and
a perfect burst-schedule ORACLE (onset-lead and trailing variants).

Conclusion drawn from the data: reactive feedback is near-optimal and dominates
every feedforward/predictive scheme -- so prediction has no headroom here and
MFDFA is NOT the root cause; the express-relief window (burst + drain tail) is
best tracked by closed-loop feedback, not anticipation.
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/rl"
os.makedirs(OUT, exist_ok=True)
EX = re.compile(r"RTRACE .* ex=(\d+)")


def hc_of(d):
    m = re.search(
        r"average_hc_packet_network_latency\s+([0-9.]+)",
        open(f"{ROOT}/{d}/stats.txt").read(),
    )
    return float(m.group(1)) if m else None


def duty_of(d):
    on = tot = 0
    p = f"{ROOT}/{d}/run.log"
    if not os.path.exists(p):
        p = f"{ROOT}/{d}/trace.log"
    for ln in open(p):
        m = EX.search(ln)
        if m:
            tot += 1
            on += int(m.group(1))
    return 100.0 * on / tot if tot else 0.0


# (label, dir, marker, color, group)
RUNS = [
    ("baseline", "m5out_rl_baseline", "s", "#777", "ref"),
    ("static-all", "m5out_rl_static", "*", "#c44e52", "ref"),
    ("reactive (feedback)", "m5out_rl_reactive", "o", "#4c72b0", "react"),
    ("MFDFA-predictive", "m5out_rl_mfdfa", "^", "#55a868", "pred"),
    ("RL $\\lambda$=0.1", "m5out_rl_deploy_lam0.1", "D", "#8172b3", "rl"),
    ("RL $\\lambda$=0.3", "m5out_rl_deploy_lam0.3", "D", "#8172b3", "rl"),
    ("RL $\\lambda$=0.6", "m5out_rl_deploy_lam0.6", "D", "#8172b3", "rl"),
    ("oracle lead=0", "m5o_lead0", "P", "#dd8452", "orc"),
    ("oracle lead=1us", "m5o_lead1000", "P", "#dd8452", "orc"),
    ("oracle lead=2us", "m5o_lead2000", "P", "#dd8452", "orc"),
    ("oracle tail on=4us", "m5t_on4", "X", "#937860", "orc"),
    ("oracle tail on=5us", "m5t_on5", "X", "#937860", "orc"),
]

pts = []
for label, d, mk, col, grp in RUNS:
    if not os.path.exists(f"{ROOT}/{d}/stats.txt"):
        print(f"  (skip missing {d})")
        continue
    hc, duty = hc_of(d), duty_of(d)
    pts.append((label, duty, hc, mk, col, grp))
    print(f"  {label:22s} duty={duty:5.1f}%  HC={hc:.0f}")

fig, ax = plt.subplots(figsize=(8.6, 5.6))
seen = set()
for label, duty, hc, mk, col, grp in pts:
    ax.scatter(
        duty,
        hc,
        s=110,
        marker=mk,
        color=col,
        zorder=3,
        edgecolor="k" if grp == "react" else "none",
        linewidth=1.2,
        label=label,
    )
# connect oracle-lead sweep + RL sweep to show their frontiers
for grp, ls in [("orc", ":"), ("rl", "--")]:
    g = sorted([(d, h) for _, d, h, _, _, gg in pts if gg == grp])
    if len(g) > 1:
        ax.plot(
            [d for d, _ in g], [h for _, h in g], ls, color="#aaa", zorder=1
        )
ax.axhline(27360, ls=":", color="#c44e52", lw=1)
ax.annotate(
    "static HC ceiling", (2, 27360), fontsize=8, color="#c44e52", va="bottom"
)
ax.set_xlabel("express duty cycle (% router-epochs on)  --  lower = cheaper")
ax.set_ylabel("Avg HC packet network latency (ticks)  --  lower = better")
ax.set_title(
    "Reactive feedback dominates every predictive/oracle scheme\n"
    "=> prediction has no headroom; MFDFA is not the root cause"
)
ax.legend(fontsize=7, ncol=2, loc="upper right")
fig.tight_layout()
fig.savefig(f"{OUT}/R4_verdict_pareto.png", dpi=140)
print(f"\nwrote {OUT}/R4_verdict_pareto.png")

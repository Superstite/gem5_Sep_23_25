#!/usr/bin/env python3
"""RL vs MFDFA vs reactive express control -- is prediction useful, and is the
MFDFA *signal* the reason predictive failed?

All numbers from gem5. Workload: SPARSE HC bursts (burst << gap) so reactive
hysteresis overshoots and there is real headroom for anticipation to cut duty.

Schemes (identical sparse+warmup load):
  baseline / static-all / reactive-global(pol1) / mfdfa-predictive(pol2) /
  rl(pol3): tabular Q-learning, trained once (eps-greedy, TD, dumps Q) then
  deployed FROZEN (greedy). Swept over the reward duty-penalty lambda to trace
  the RL HC-vs-duty Pareto frontier.

Verdict:
  * RL frontier passes below/left of the reactive point  -> the MFDFA signal was
    the limitation (a learned predictor extracts the headroom). MFDFA not the way.
  * RL cannot beat reactive either -> little predictive headroom here; MFDFA is
    NOT the root cause -- reactive already near the static ceiling.
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
OUT = f"{ROOT}/scripts/recon_results/rl"
os.makedirs(OUT, exist_ok=True)

HC_SRCS = "0,3,10,20,29,35,48,59"
EPOCH = 100
# SPARSE bursts: 2000ns on, 6000ns off -> ~25% active floor, room to beat 40%.
LOAD = [
    "--duration",
    "0.1ms",
    "--hc-rate",
    "8GiB/s",
    "--lc-rate",
    "2GiB/s",
    "--high-crit-srcs",
    HC_SRCS,
    "--routing-algo",
    "2",
    "--epoch",
    str(EPOCH),
    "--hc-burst",
    "2000ns",
    "--hc-gap",
    "6000ns",
    "--hc-warmup",
    "5000ns",
]
RTRACE = re.compile(
    r"RTRACE t=(\d+) R\d+ flits=\d+ mc=\d+ hc=(\d+) lc=\d+ "
    r"hcocc=\d+ dnocc=\d+ ex=(\d+)"
)
RLLOG = re.compile(r"RECONF_RL s=\d+ a=\d+ r=(-?[0-9.]+) occ=(\d+)")


def run(name, flags, trace=True):
    od = f"{ROOT}/m5out_rl_{name}"
    os.makedirs(od, exist_ok=True)
    log = f"{od}/run.log"
    cmd = [GEM5, f"--outdir={od}"]
    if trace:
        cmd += [
            (
                "--debug-flags=ReconTrace,RubyNetwork"
                if "train" in name
                else "--debug-flags=ReconTrace"
            )
        ]
    cmd += [CFG] + LOAD + flags
    print(f"[run] {name}", flush=True)
    with open(log, "w") as fh:
        subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, check=False)
    return od, log


def parse(log):
    per_t, on, tot = {}, {}, {}
    with open(log) as fh:
        for ln in fh:
            m = RTRACE.search(ln)
            if not m:
                continue
            t, hc, ex = int(m.group(1)), int(m.group(2)), int(m.group(3))
            per_t[t] = per_t.get(t, 0) + hc
            tot[t] = tot.get(t, 0) + 1
            on[t] = on.get(t, 0) + ex
    ts = sorted(per_t)
    hc = np.array([per_t[t] for t in ts], float)
    duty = np.array([on[t] / tot[t] for t in ts]) if ts else np.array([])
    return np.array(ts), hc, duty


def stat(od, key):
    m = re.search(
        rf"{re.escape(key)}\s+([0-9.]+)", open(f"{od}/stats.txt").read()
    )
    return float(m.group(1)) if m else float("nan")


def metrics(od, log):
    _, _, duty = parse(log)
    return dict(
        hc=stat(od, "network.average_hc_packet_network_latency"),
        lc=stat(od, "network.average_lc_packet_network_latency"),
        duty=float(np.mean(duty)) * 100 if len(duty) else 0.0,
    )


# ---- calibrate demand thresholds from a static probe ---------------------
odp, logp = run(
    "probe",
    [
        "--express-active",
        "1",
        "--reconfig",
        "1",
        "--reconfig-policy",
        "1",
        "--hc-hi",
        "999999999",
        "--hc-lo",
        "0",
    ],
)
_, hc_series, _ = parse(logp)
HI = int(np.percentile(hc_series, 70))
LO = max(1, int(np.percentile(hc_series, 35)))
SL = int(0.5 * (np.percentile(hc_series, 90) - np.median(hc_series)))
print(f"  calibrated HI={HI} LO={LO} slope={SL}", flush=True)
THR = ["--hc-hi", str(HI), "--hc-lo", str(LO)]

res = {}
res["baseline"] = metrics(*run("baseline", ["--routing-algo", "1"]))
res["static_all"] = metrics(
    *run(
        "static",
        [
            "--express-active",
            "1",
            "--reconfig",
            "1",
            "--reconfig-policy",
            "1",
            "--hc-hi",
            "999999999",
            "--hc-lo",
            "0",
        ],
    )
)
res["reactive"] = metrics(
    *run("reactive", ["--reconfig", "1", "--reconfig-policy", "1"] + THR)
)
res["mfdfa"] = metrics(
    *run(
        "mfdfa",
        [
            "--reconfig",
            "1",
            "--reconfig-policy",
            "2",
            "--slope-hi",
            str(SL),
            "--hold-epochs",
            "4",
            "--ewma-alpha",
            "0.4",
        ]
        + THR,
    )
)

# ---- RL: train (dump Q) then deploy frozen, across lambda -----------------
rl_points = []
for lam in [0.1, 0.3, 0.6, 1.0]:
    q = f"{OUT}/q_lam{lam}.txt"
    rl_common = [
        "--reconfig",
        "1",
        "--reconfig-policy",
        "3",
        "--q-file",
        q,
        "--rl-lambda",
        str(lam),
        "--rl-occ-scale",
        "15",
        "--ewma-alpha",
        "0.4",
    ] + THR
    run(f"train_lam{lam}", rl_common + ["--rl-train", "1", "--rl-eps", "0.2"])
    m = metrics(*run(f"deploy_lam{lam}", rl_common + ["--rl-train", "0"]))
    m["lam"] = lam
    rl_points.append(m)
    res[f"rl_lam{lam}"] = m
    print(
        f"    rl lambda={lam}: HC={m['hc']:.0f} duty={m['duty']:.0f}%",
        flush=True,
    )

for k, v in res.items():
    print(f"  {k:14s} HC={v['hc']:.0f} LC={v['lc']:.0f} duty={v['duty']:.0f}%")

# ---- R1: HC-vs-duty Pareto (the decisive figure) -------------------------
fig, ax = plt.subplots(figsize=(7.6, 5.2))


def pt(name, marker, color, label):
    ax.scatter(
        res[name]["duty"],
        res[name]["hc"],
        s=90,
        marker=marker,
        color=color,
        zorder=3,
        label=label,
    )


pt("baseline", "s", "#777", "baseline (no express)")
pt("static_all", "*", "#c44e52", "static-all")
pt("reactive", "o", "#4c72b0", "reactive-global")
pt("mfdfa", "^", "#55a868", "MFDFA-predictive")
rl_d = [p["duty"] for p in rl_points]
rl_h = [p["hc"] for p in rl_points]
order = np.argsort(rl_d)
ax.plot(
    np.array(rl_d)[order],
    np.array(rl_h)[order],
    "D--",
    color="#8172b3",
    zorder=2,
    label="RL (Q-learning) frontier",
)
for p in rl_points:
    ax.annotate(
        f"$\\lambda$={p['lam']}",
        (p["duty"], p["hc"]),
        textcoords="offset points",
        xytext=(6, 4),
        fontsize=7,
    )
ax.axhline(
    res["static_all"]["hc"],
    ls=":",
    color="#c44e52",
    lw=1,
    label="static HC (ceiling)",
)
ax.set_xlabel("express duty cycle (% router-epochs on)")
ax.set_ylabel("Avg HC packet network latency (ticks)")
ax.set_title(
    "HC latency vs express duty: does a learned predictor beat "
    "reactive?\n(down-left = better)"
)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(f"{OUT}/R1_pareto.png", dpi=140)
plt.close(fig)

# ---- R2: RL learning curve (reward per epoch during training) ------------
best_lam = min(rl_points, key=lambda p: p["hc"] + 0.01 * p["duty"])["lam"]
tr_log = f"{ROOT}/m5out_rl_train_lam{best_lam}/run.log"
rew = []
with open(tr_log) as fh:
    for ln in fh:
        m = RLLOG.search(ln)
        if m:
            rew.append(float(m.group(1)))
if rew:
    rew = np.array(rew)
    k = max(1, len(rew) // 50)
    sm = np.convolve(rew, np.ones(k) / k, mode="valid")
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(sm, color="#8172b3")
    ax.set_xlabel("training epoch")
    ax.set_ylabel("reward (smoothed)")
    ax.set_title(
        f"RL learning curve (lambda={best_lam}): "
        "reward improves as Q converges"
    )
    fig.tight_layout()
    fig.savefig(f"{OUT}/R2_learning.png", dpi=140)
    plt.close(fig)

# ---- R3: deployed RL express timeline vs HC bursts -----------------------
dep = f"{ROOT}/m5out_rl_deploy_lam{best_lam}/run.log"
tsd, hcd, dutyd = parse(dep)
fig, ax = plt.subplots(figsize=(9, 4))
ax.fill_between(
    tsd / 1000,
    0,
    hcd / (hcd.max() or 1),
    color="#c44e52",
    alpha=0.25,
    label="HC demand (norm)",
)
ax.plot(tsd / 1000, dutyd, color="#8172b3", lw=1.6, label="RL express duty")
ax.set_xlabel("time (kcycles)")
ax.set_ylabel("fraction")
ax.set_title(
    f"Deployed RL (frozen Q, lambda={best_lam}): learned express "
    "gating vs HC bursts"
)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(f"{OUT}/R3_timeline.png", dpi=140)
plt.close(fig)

print(f"\n[done] -> {OUT}")
for f in sorted(os.listdir(OUT)):
    if f.endswith(".png"):
        print("   ", f)

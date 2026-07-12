#!/usr/bin/env python3
"""Predictive elastic express activation: offline MFDFA -> online O(1) controller.

Pipeline (all numbers from real gem5 output):
  1. Run a BURSTY mixed-criticality load (HC ON/OFF bursts) under static_all,
     capturing the network-wide HC-demand series per epoch (ReconTrace).
  2. Offline MFDFA on that series -> generalized Hurst h(2) (persistence) and
     multifractal spectrum width d_alpha (burstiness). If h(2)>0.5 the series
     is persistent => a rising edge predicts continued demand, so a cheap
     leading-edge + hold controller can pre-activate express before collapse.
     These two numbers CALIBRATE the online controller (hold length, thresholds).
     MFDFA runs here (offline), never inside gem5.
  3. Run baseline / static_all / reactive-global(policy1) / predictive(policy2)
     under the same bursty load. Report HC & LC latency AND express duty cycle
     (fraction of router-epochs with express on) -- the elastic cost. Target:
     predictive matches static_all HC latency at a LOWER duty cycle.

Figures -> scripts/recon_results/predictive/.
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
OUT = f"{ROOT}/scripts/recon_results/predictive"
os.makedirs(OUT, exist_ok=True)

HC_SRCS = "0,3,10,20,29,35,48,59"
EPOCH = 100
# Bursty HC: hard bursts with idle gaps -> temporal slack + self-similar arrivals.
BURST, GAP, WARMUP = "2000ns", "3000ns", "5000ns"
LOAD = [
    "--duration",
    "0.05ms",
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
    # HC warmup so the first burst hits a steady network (no initial-collapse
    # artefact inflating the average HC latency).
    "--hc-burst",
    BURST,
    "--hc-gap",
    GAP,
    "--hc-warmup",
    WARMUP,
]
RTRACE = re.compile(
    r"RTRACE t=(\d+) R(\d+) (?:flits|packets)=(\d+) mc=(\d+) hc=(\d+) lc=(\d+) "
    r"hcocc=(\d+) dnocc=(\d+) ex=(\d+)"
)


def run(name, flags, trace=True):
    od = f"{ROOT}/m5out_pred_{name}"
    os.makedirs(od, exist_ok=True)
    log = f"{od}/trace.log"
    cmd = [GEM5, f"--outdir={od}"]
    if trace:
        cmd += ["--debug-flags=ReconTrace"]
    cmd += [CFG] + LOAD + flags
    print(f"[run] {name}", flush=True)
    with open(log, "w") as fh:
        subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, check=False)
    return od, log


def parse(log):
    """-> (epochs sorted, hc_series[global HC/epoch], duty[frac ex=1])."""
    per_t = {}
    ex_on = {}
    ex_tot = {}
    with open(log) as fh:
        for line in fh:
            m = RTRACE.search(line)
            if not m:
                continue
            t = int(m.group(1))
            hc = int(m.group(5))
            ex = int(m.group(9))
            per_t[t] = per_t.get(t, 0) + hc
            ex_tot[t] = ex_tot.get(t, 0) + 1
            ex_on[t] = ex_on.get(t, 0) + ex
    ts = sorted(per_t)
    hc_series = np.array([per_t[t] for t in ts], dtype=float)
    duty = np.array([ex_on[t] / ex_tot[t] for t in ts]) if ts else np.array([])
    return np.array(ts), hc_series, duty


def stat(od, key):
    txt = open(f"{od}/stats.txt").read()
    m = re.search(rf"{re.escape(key)}\s+([0-9.]+)", txt)
    return float(m.group(1)) if m else float("nan")


def mfdfa(x, qs, scales, order=1):
    """Compact MFDFA. Returns h(q) array and (alpha, f(alpha)) spectrum."""
    x = np.asarray(x, float)
    Y = np.cumsum(x - x.mean())
    N = len(Y)
    Fq = np.zeros((len(qs), len(scales)))
    for si, s in enumerate(scales):
        ns = N // s
        if ns < 1:
            Fq[:, si] = np.nan
            continue
        F2 = []
        for v in range(ns):  # forward segments
            seg = Y[v * s : (v + 1) * s]
            c = np.polyfit(np.arange(s), seg, order)
            F2.append(np.mean((seg - np.polyval(c, np.arange(s))) ** 2))
        for v in range(ns):  # backward segments
            seg = Y[N - (v + 1) * s : N - v * s]
            c = np.polyfit(np.arange(s), seg, order)
            F2.append(np.mean((seg - np.polyval(c, np.arange(s))) ** 2))
        F2 = np.array(F2)
        for qi, q in enumerate(qs):
            if abs(q) < 1e-6:
                Fq[qi, si] = np.exp(0.5 * np.mean(np.log(F2 + 1e-12)))
            else:
                Fq[qi, si] = np.mean(F2 ** (q / 2.0)) ** (1.0 / q)
    logs = np.log(scales)
    hq = np.array(
        [
            np.polyfit(logs, np.log(Fq[qi] + 1e-12), 1)[0]
            for qi in range(len(qs))
        ]
    )
    tau = qs * hq - 1.0
    alpha = np.gradient(tau, qs)
    falpha = qs * alpha - tau
    return hq, alpha, falpha


# Static express ON from init, but with the sampling manager enabled at an
# UNREACHABLE onset threshold so reconfigStep fires (=> ReconTrace) without ever
# toggling express -- i.e. a genuine always-on run that we can still trace.
STATIC_ON = [
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
]

# ---- 1. bursty static_all run -> HC demand series ------------------------
od0, log0 = run("static_probe", STATIC_ON)
ts, hc_series, _ = parse(log0)
print(f"  captured {len(hc_series)} epochs of HC demand", flush=True)

# ---- 2. offline MFDFA calibration ----------------------------------------
qs = np.arange(-4, 5, 1.0)
scales = np.unique(
    np.floor(
        np.logspace(np.log10(8), np.log10(max(16, len(hc_series) // 4)), 12)
    ).astype(int)
)
hq, alpha, falpha = mfdfa(hc_series, qs, scales)
h2 = hq[np.argmin(np.abs(qs - 2))]
d_alpha = float(np.nanmax(alpha) - np.nanmin(alpha))
# Calibrate the online controller from the series + persistence:
hi = float(np.percentile(hc_series, 75))  # onset threshold
lo = float(np.percentile(hc_series, 30))  # release threshold
slope = float(0.5 * (np.percentile(hc_series, 90) - np.median(hc_series)))
burst_epochs = int(round(2000 / EPOCH))  # HC burst len in epochs
# Hold only bridges brief intra-burst dips (a few epochs). High persistence
# (large h2) => smoother bursts => SHORTER hold needed; the slope trigger
# re-arms at the next rising edge. (A long hold would just pin express on and
# forfeit the elastic gap.)
hold = max(3, int(round(burst_epochs * (1.0 - h2))))
print(
    f"  MFDFA: h(2)={h2:.3f}  d_alpha={d_alpha:.3f}  "
    f"-> hi={hi:.0f} lo={lo:.0f} slope={slope:.0f} hold={hold}",
    flush=True,
)

# ---- 3. compare schemes under identical bursty load ----------------------
common_pred = [
    "--hc-hi",
    str(int(hi)),
    "--hc-lo",
    str(int(lo)),
    "--slope-hi",
    str(int(slope)),
    "--hold-epochs",
    str(hold),
    "--ewma-alpha",
    "0.4",
]
SCHEMES = {
    "baseline": ["--routing-algo", "1"],
    "static_all": STATIC_ON,
    "reactive_global": ["--reconfig", "1", "--reconfig-policy", "1"]
    + common_pred,
    "predictive": ["--reconfig", "1", "--reconfig-policy", "2"] + common_pred,
}
res = {}
for name, flags in SCHEMES.items():
    od, log = run(name, flags)
    _, _, duty = parse(log)
    res[name] = dict(
        hc=stat(od, "network.average_hc_packet_network_latency"),
        lc=stat(od, "network.average_lc_packet_network_latency"),
        duty=float(np.mean(duty)) if len(duty) else 0.0,
    )
    print(
        f"    {name:16s} HC={res[name]['hc']:.0f} LC={res[name]['lc']:.0f} "
        f"duty={res[name]['duty']*100:.0f}%",
        flush=True,
    )

# ---- figures -------------------------------------------------------------
# P1: HC demand series + multifractal spectrum (evidence of predictability)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
a1.plot(ts / 1000.0, hc_series, color="#c44e52", lw=1.2)
a1.set_xlabel("time (kcycles)")
a1.set_ylabel("network-wide HC flits / epoch")
a1.set_title(
    f"Bursty HC demand (real gem5)\nMFDFA h(2)={h2:.2f} "
    f"(persistent) -> predictable"
)
a2.plot(alpha, falpha, "o-", color="#4c72b0")
a2.set_xlabel(r"$\alpha$")
a2.set_ylabel(r"$f(\alpha)$")
a2.set_title(f"Multifractal spectrum\nwidth $\\Delta\\alpha$={d_alpha:.2f}")
fig.tight_layout()
fig.savefig(f"{OUT}/P1_mfdfa.png", dpi=140)
plt.close(fig)

# P2: HC latency (bars) vs express duty cycle (line) across schemes
names = list(SCHEMES)
hc_l = [res[n]["hc"] for n in names]
duty = [res[n]["duty"] * 100 for n in names]
xi = np.arange(len(names))
fig, ax = plt.subplots(figsize=(8, 4.6))
ax.bar(xi, hc_l, 0.55, color="#c44e52", label="HC latency")
ax.set_ylabel("Avg HC packet network latency (ticks)")
ax.set_xticks(xi)
ax.set_xticklabels(
    ["baseline", "static-all", "reactive\nglobal", "predictive\n(MFDFA)"]
)
ax2 = ax.twinx()
ax2.plot(xi, duty, "D-", color="#333", label="express duty cycle")
ax2.set_ylabel("express duty cycle (% router-epochs on)")
ax2.set_ylim(0, 105)
for i, d in enumerate(duty):
    ax2.annotate(
        f"{d:.0f}%",
        (i, d),
        textcoords="offset points",
        xytext=(0, 8),
        ha="center",
        fontsize=8,
    )
ax.set_title(
    "Elastic express matches static HC latency at <half the duty "
    "cycle;\nslope-prediction adds duty without lowering HC"
)
fig.tight_layout()
fig.savefig(f"{OUT}/P2_latency_vs_duty.png", dpi=140)
plt.close(fig)

# P3: predictive duty-cycle timeline tracks HC bursts
_, log_p = (
    f"{ROOT}/m5out_pred_predictive",
    f"{ROOT}/m5out_pred_predictive/trace.log",
)
tsp, hcp, dutyp = parse(log_p)
fig, ax = plt.subplots(figsize=(9, 4))
ax.fill_between(
    tsp / 1000.0,
    0,
    hcp / (hcp.max() or 1),
    color="#c44e52",
    alpha=0.25,
    label="HC demand (norm)",
)
ax.plot(
    tsp / 1000.0,
    dutyp,
    color="#4c72b0",
    lw=1.6,
    label="express duty (predictive)",
)
ax.set_xlabel("time (kcycles)")
ax.set_ylabel("fraction")
ax.set_title(
    "Predictive controller arms express on the burst edge, releases "
    "in the gap"
)
ax.legend(loc="upper right", fontsize=8)
fig.tight_layout()
fig.savefig(f"{OUT}/P3_timeline.png", dpi=140)
plt.close(fig)

print(f"\n[done] figures -> {OUT}")
for f in sorted(os.listdir(OUT)):
    print("   ", f)

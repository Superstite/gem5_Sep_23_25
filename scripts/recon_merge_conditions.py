#!/usr/bin/env python3
"""When is elastic VC merging useful? Synthetic bursty HC + swept LC rate
(= donor-VC availability). Merge helps only when HC is VC-starved at the sink
AND the donor is idle. For each LC rate compare merge OFF (static isolation)
vs merge FORCED (always armed = ceiling) under always-on express (max funnel).
Real gem5.
"""
import csv
import os
import re
import subprocess

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
GEM5 = f"{ROOT}/build/X86_MESI_Two_Level/gem5.debug"
CFG = f"{ROOT}/configs/network/recon_traffic.py"
OUT = f"{ROOT}/scripts/recon_results/merge"
os.makedirs(OUT, exist_ok=True)

# strong HC bursts + always-on express so HC funnels hard into the MC sinks
BASE = [
    "--duration",
    "0.1ms",
    "--hc-rate",
    "16GiB/s",
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
    "--routing-algo",
    "2",
    "--express-active",
    "1",
]
LC_RATES = ["0.1GiB/s", "0.5GiB/s", "1GiB/s", "2GiB/s", "4GiB/s"]
MERGE_OFF = ["--mc-merge", "0"]
MERGE_ON = ["--mc-merge", "1", "--mc-hc-hi", "1", "--mc-lc-lo", "999999"]


def run(tag, flags):
    od = f"{ROOT}/m5cond_{tag}"
    os.makedirs(od, exist_ok=True)
    if (
        not os.path.exists(f"{od}/stats.txt")
        or os.path.getsize(f"{od}/stats.txt") == 0
    ):
        subprocess.run(
            [GEM5, f"--outdir={od}", CFG] + BASE + flags,
            stdout=open(f"{od}/run.log", "w"),
            stderr=subprocess.STDOUT,
            check=False,
        )
    txt = open(f"{od}/stats.txt").read()

    def g(k):
        m = re.search(rf"average_{k}_packet_network_latency\s+([0-9.]+)", txt)
        return float(m.group(1)) if m else float("nan")

    return g("hc"), g("lc")


rows = [
    (
        "lc_rate",
        "hc_iso",
        "hc_merge",
        "hc_benefit_%",
        "lc_iso",
        "lc_merge",
        "lc_degr_%",
    )
]
for lc in LC_RATES:
    tag = lc.replace("/", "").replace(".", "p")
    hc0, lc0 = run(f"off_{tag}", ["--lc-rate", lc] + MERGE_OFF)
    hc1, lc1 = run(f"on_{tag}", ["--lc-rate", lc] + MERGE_ON)
    hb = 100 * (hc0 - hc1) / hc0
    ld = 100 * (lc1 - lc0) / lc0
    rows.append((lc, hc0, hc1, hb, lc0, lc1, ld))
    print(
        f"LC={lc:8s} HC iso={hc0:.0f} merge={hc1:.0f} ({hb:+.1f}%)  "
        f"LC iso={lc0:.0f} merge={lc1:.0f} ({ld:+.1f}%)",
        flush=True,
    )

with open(f"{OUT}/conditions.csv", "w", newline="") as fh:
    csv.writer(fh).writerows(rows)
print(f"\n[done] -> {OUT}/conditions.csv")

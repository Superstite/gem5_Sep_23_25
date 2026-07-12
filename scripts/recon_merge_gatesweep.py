#!/usr/bin/env python3
"""Sweep the elastic-VC-merge gate constants (mc_hc_hi = F1 HC-demand arm,
mc_lc_lo = F2 donor-idle threshold) on the REAL MiBench workload, to find the
gate that gives the most HC-latency benefit at the least LC degradation.

iso baseline = reactive express, merge OFF (m5real_react_duty, 25M ticks).
Each sweep point = reactive express + merge ON with a (hc_hi, lc_lo) gate.
All runs 25M ticks (same window as iso). Real gem5.
"""
import csv
import os
import re
import subprocess

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
GEM5 = f"{ROOT}/build/X86_MESI_Two_Level/gem5.debug"
CFG = f"{ROOT}/configs/network/recon_bench_run.py"
OUT = f"{ROOT}/scripts/recon_results/merge"
os.makedirs(OUT, exist_ok=True)
BASE = [
    "--routing-algo",
    "2",
    "--reconfig-policy",
    "1",
    "--hc-hi",
    "24",
    "--hc-lo",
    "10",
    "--max-ticks",
    "25000000",
]
HC_HI = [1, 4, 8]  # F1: HC pkts/epoch to arm (MC HC max ~14)
LC_LO = [30, 50, 999999]  # F2: donor-idle LC threshold (LC median ~39)


def lat(d, crit):
    m = re.search(
        rf"average_{crit}_packet_network_latency\s+([0-9.]+)",
        open(f"{ROOT}/{d}/stats.txt").read(),
    )
    return float(m.group(1))


# iso baseline (merge off) already run as m5real_react_duty
iso_hc, iso_lc = lat("m5real_react_duty", "hc"), lat("m5real_react_duty", "lc")
print(f"iso (merge off): HC={iso_hc:.0f} LC={iso_lc:.0f}")

rows = [("gate", "hc_hi", "lc_lo", "hc", "lc", "hc_benefit_%", "lc_degr_%")]
for hi in HC_HI:
    for lo in LC_LO:
        od = f"{ROOT}/m5real_g_{hi}_{lo}"
        os.makedirs(od, exist_ok=True)
        if (
            not os.path.exists(f"{od}/stats.txt")
            or os.path.getsize(f"{od}/stats.txt") == 0
        ):
            print(f"[run] hc_hi={hi} lc_lo={lo}", flush=True)
            with open(f"{od}/run.log", "w") as fh:
                subprocess.run(
                    [GEM5, f"--outdir={od}", CFG]
                    + BASE
                    + [
                        "--mc-merge",
                        "1",
                        "--mc-hc-hi",
                        str(hi),
                        "--mc-lc-lo",
                        str(lo),
                    ],
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
        hc, lc = lat(f"m5real_g_{hi}_{lo}", "hc"), lat(
            f"m5real_g_{hi}_{lo}", "lc"
        )
        hb = 100 * (iso_hc - hc) / iso_hc  # +ve = HC improved
        ld = 100 * (lc - iso_lc) / iso_lc  # +ve = LC degraded
        rows.append((f"{hi}/{lo}", hi, lo, hc, lc, hb, ld))
        print(
            f"  hc_hi={hi:>2} lc_lo={lo:>6}  HC={hc:.0f} ({hb:+.2f}%)  "
            f"LC={lc:.0f} ({ld:+.2f}%)",
            flush=True,
        )

with open(f"{OUT}/gatesweep.csv", "w", newline="") as fh:
    csv.writer(fh).writerows(rows)
print(f"\n[done] -> {OUT}/gatesweep.csv")

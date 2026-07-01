#!/usr/bin/env python3
"""Phase 6 evaluation: reconfigurable-topology HC/LC latency + throughput.

Runs three schemes on an identical congested mixed-criticality load and reports
per-criticality network latency (the metric the whole project targets):
  baseline    : XY, no express links
  static_all  : custom routing, all express links always active
  reconfig    : custom routing, runtime manager toggles express on hot routers

Emits a table + a bar chart (HC vs LC latency per scheme).
"""
import csv
import os
import re
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
GEM5 = f"{ROOT}/build/X86_MESI_Two_Level/gem5.debug"
CFG = f"{ROOT}/configs/network/recon_traffic.py"
OUT = f"{ROOT}/scripts/recon_results"
os.makedirs(OUT, exist_ok=True)

# HC minority (8 of 64), placed across the mesh; both classes driven hard so the
# shared mesh genuinely congests and HC needs relief.
HC = "0,3,10,20,29,35,48,59"
LOAD = [
    "--duration",
    "0.05ms",
    "--hc-rate",
    "2GiB/s",
    "--lc-rate",
    "2GiB/s",
    "--high-crit-srcs",
    HC,
    "--routing-algo",
    "2",
]

SCHEMES = {
    "baseline": ["--express-active", "0", "--reconfig", "0"],
    "static_all": ["--express-active", "1", "--reconfig", "0"],
    "reconfig": [
        "--reconfig",
        "1",
        "--epoch",
        "5000",
        "--high-wm",
        "400",
        "--low-wm",
        "150",
    ],
}


def stat(txt, key):
    m = re.search(rf"{re.escape(key)}\s+([0-9.]+)", txt)
    return float(m.group(1)) if m else float("nan")


rows = []
for name, flags in SCHEMES.items():
    od = f"{ROOT}/m5out_eval_{name}"
    os.makedirs(od, exist_ok=True)
    subprocess.run(
        [GEM5, f"--outdir={od}", CFG] + LOAD + flags,
        stdout=open(f"{od}/run.log", "w"),
        stderr=subprocess.STDOUT,
        check=False,
    )
    st = open(f"{od}/stats.txt").read()
    hc = stat(st, "network.average_hc_packet_network_latency")
    lc = stat(st, "network.average_lc_packet_network_latency")
    hc_n = stat(st, "network.hc_packets_received")
    lc_n = stat(st, "network.lc_packets_received")
    hops = stat(st, "network.average_hops")
    rows.append((name, hc, lc, hc_n, lc_n, hops))
    print(
        f"{name:11s} HC_lat={hc:.1f} LC_lat={lc:.1f} "
        f"HC_pkts={hc_n:.0f} LC_pkts={lc_n:.0f} hops={hops:.3f}"
    )

with open(f"{OUT}/eval.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(
        [
            "scheme",
            "hc_net_lat",
            "lc_net_lat",
            "hc_pkts",
            "lc_pkts",
            "avg_hops",
        ]
    )
    w.writerows(rows)

# Deltas vs baseline
base = {r[0]: r for r in rows}["baseline"]
print("\n-- vs baseline --")
for name, hc, lc, hc_n, lc_n, hops in rows:
    if name == "baseline":
        continue
    print(
        f"{name:11s} HC_lat {(hc/base[1]-1)*100:+.1f}%  "
        f"LC_lat {(lc/base[2]-1)*100:+.1f}%  "
        f"HC_thru {(hc_n/base[3]-1)*100:+.1f}%  "
        f"LC_thru {(lc_n/base[4]-1)*100:+.1f}%"
    )

# Bar chart
names = [r[0] for r in rows]
hc_l = [r[1] for r in rows]
lc_l = [r[2] for r in rows]
x = range(len(names))
w = 0.38
fig, ax = plt.subplots(figsize=(6.5, 4.2))
ax.bar([i - w / 2 for i in x], hc_l, w, label="HC", color="#c44e52")
ax.bar([i + w / 2 for i in x], lc_l, w, label="LC", color="#4c72b0")
ax.set_xticks(list(x))
ax.set_xticklabels(names)
ax.set_ylabel("Avg packet network latency (ticks)")
ax.set_title("HC vs LC latency: baseline / static-all / reconfig")
ax.legend()
fig.tight_layout()
fig.savefig(f"{OUT}/fig_hc_lc_latency.png", dpi=140)
print(f"\nwrote {OUT}/eval.csv + fig_hc_lc_latency.png")

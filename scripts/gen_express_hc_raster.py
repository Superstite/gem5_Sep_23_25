#!/usr/bin/env python3
"""Space-time map: at what time did WHICH router's express link carry HC traffic
(reactive strategy). Short window. Real gem5 -- each RECONF_EXPRESS log line is
one HC PACKET routed onto a 2-hop express outport at a router (route compute runs
once per packet, at the head flit; all its flits follow that outport).
FIG2/FIG3 bold style, PDF.
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
OUT = f"{ROOT}/scripts/recon_results/summary"
OD = f"{ROOT}/m5out_expraster"
EPOCH_CYC = 100
TPC = 1000  # ticks per cycle
BIN = EPOCH_CYC * TPC  # 1 epoch = 100000 ticks
MC = {21, 42}

os.makedirs(OD, exist_ok=True)
if not os.path.exists(f"{OD}/express.log"):
    # short run so the RubyNetwork (per-flit) log stays manageable
    with open(f"{OD}/run.log", "w") as fh:
        subprocess.run(
            [
                GEM5,
                f"--outdir={OD}",
                "--debug-flags=RubyNetwork",
                CFG,
                "--duration",
                "0.03ms",
                "--hc-rate",
                "8GiB/s",
                "--lc-rate",
                "2GiB/s",
                "--high-crit-srcs",
                "0,3,10,20,29,35,48,59",
                "--routing-algo",
                "2",
                "--epoch",
                "100",
                "--hc-burst",
                "2000ns",
                "--hc-gap",
                "6000ns",
                "--hc-warmup",
                "5000ns",
                "--reconfig",
                "1",
                "--reconfig-policy",
                "1",
                "--hc-hi",
                "40",
                "--hc-lo",
                "1",
            ],
            stdout=fh,
            stderr=subprocess.STDOUT,
            check=False,
        )
    # extract just the express lines
    with open(f"{OD}/run.log") as fi, open(f"{OD}/express.log", "w") as fo:
        for ln in fi:
            if "RECONF_EXPRESS" in ln:
                fo.write(ln)

RE = re.compile(r"^\s*(\d+):.*RECONF_EXPRESS R(\d+)->")
cnt = {}
for ln in open(f"{OD}/express.log"):
    m = RE.search(ln)
    if m:
        ep = int(m.group(1)) // BIN
        r = int(m.group(2))
        cnt[(ep, r)] = cnt.get((ep, r), 0) + 1

if not cnt:
    raise SystemExit("no RECONF_EXPRESS lines parsed")
eps = sorted({e for e, _ in cnt})
routers = sorted({r for _, r in cnt})
e0 = eps[0]
ne = eps[-1] - e0 + 1
M = np.zeros((len(routers), ne))
ridx = {r: i for i, r in enumerate(routers)}
for (e, r), c in cnt.items():
    M[ridx[r], e - e0] = c
print(
    f"routers carrying express-HC={len(routers)}  epochs={ne}  "
    f"total HC packets via express={int(M.sum())}"
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
FONT_AXIS = 15
fig, ax = plt.subplots(figsize=(8.2, 5.0))
im = ax.imshow(
    M,
    aspect="auto",
    cmap="turbo",
    origin="upper",
    interpolation="nearest",
    extent=[e0, e0 + ne, len(routers) - 0.5, -0.5],
)
ax.set_yticks(range(len(routers)))
ax.set_yticklabels(
    [f"R{r}" + ("  [MC]" if r in MC else "") for r in routers], fontsize=11
)
ax.set_xlabel(f"Time (t: epochs of {EPOCH_CYC} cycles)", fontsize=FONT_AXIS)
ax.set_ylabel("Mesh router (Express link)", fontsize=FONT_AXIS)
cb = fig.colorbar(im, ax=ax, pad=0.02, aspect=26)
cb.set_label(
    "HC packets routed via express / epoch", fontsize=13, fontweight="bold"
)
cb.ax.tick_params(labelsize=11)
for lbl in ax.get_xticklabels():
    lbl.set_fontweight("bold")
fig.tight_layout()
fig.savefig(f"{OUT}/F7_express_hc_raster.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F7_express_hc_raster.pdf")

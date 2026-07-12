#!/usr/bin/env python3
"""Total-NoC energy via DSENT (45 nm electrical mesh), express links/ports gated
by the measured reactive duty. Compares baseline (no express), static-all
express (always on), reactive express (duty-gated). Real DSENT component power
x real link/router counts x measured duty.

DSENT built as build/ext/dsent/dsent.so (interface.cc ported to Python 3).
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/summary"
sys.path.append(f"{ROOT}/build/ext/dsent")
import dsent

FREQ = 1_000_000_000  # 1 GHz
FLIT_BITS = 128  # ni_flit_size 16 B
NVNET, VCS, BUFS = 5, 4, 4
N_ROUTER = 64
N_BASE_LINK = 224  # East/West/North/South 1-hop
N_EXPR_LINK = 192  # TwoHop E/W/N/S (the gated express fabric)
DUTY_REACT = 0.68  # measured reactive express duty (F15/F6)
T = 25000 / FREQ  # 25000-cycle run window (s)


def _sum(tpl):
    dyn = leak = 0.0
    for n, v in tpl:
        if "Dynamic power" in n:
            dyn = v
        elif "Leakage power" in n:
            leak = v
    return dyn + leak


def router_power(ports):
    dsent.initialize(f"{ROOT}/ext/dsent/configs/router.cfg")
    p = _sum(
        dsent.computeRouterPowerAndArea(
            FREQ, ports, ports, NVNET, VCS, BUFS, FLIT_BITS
        )
    )
    dsent.finalize()
    return p


def link_power():
    dsent.initialize(f"{ROOT}/ext/dsent/configs/electrical-link.cfg")
    p = _sum(dsent.computeLinkPower(FREQ))
    dsent.finalize()
    return p


P_rtr5 = router_power(5)  # base router: 4 mesh + 1 local port
P_rtr9 = router_power(9)  # + 4 express (2-hop) ports
P_expr_port = P_rtr9 - P_rtr5  # express-port (buffer/xbar/SA) cost per router
P_link = link_power()
print(
    f"DSENT: P_rtr5={P_rtr5*1e3:.2f}mW P_rtr9={P_rtr9*1e3:.2f}mW "
    f"P_expr_port={P_expr_port*1e3:.2f}mW P_link={P_link*1e3:.3f}mW"
)

# always-on = base routers + base mesh links
P_fixed = N_ROUTER * P_rtr5 + N_BASE_LINK * P_link
# gated express resource = express router ports + express links
P_express = N_ROUTER * P_expr_port + N_EXPR_LINK * P_link
print(f"P_fixed={P_fixed:.3f}W  P_express(full)={P_express:.3f}W")

frac = {
    "Baseline\n(No Express)": 0.0,
    "Static (Always-ON)\nExpress": 1.0,
    "Reactive\nExpress": DUTY_REACT,
}
E = {k: (P_fixed + P_express * f) * T for k, f in frac.items()}  # Joules
names = list(frac)
En = [E[k] / E[names[0]] for k in names]  # norm to baseline
print("Total NoC energy (uJ):", {k: f"{E[k]*1e6:.2f}" for k in names})
sv_stat = 100 * (E[names[1]] - E[names[2]]) / E[names[1]]  # react vs static
print(f"reactive vs static total-NoC saving = {sv_stat:.1f}%")

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    }
)
fig, ax = plt.subplots(figsize=(7.2, 5.0))
# baseline blue, static-always-on rust, reactive green
cols = ["#1a53ff", "#B7410E", "#2ca02c"]
bars = ax.bar(
    range(3),
    En,
    0.6,
    color=cols,
    edgecolor="black",
    linewidth=1.2,
    hatch=["---", "//", "\\\\"],
)
ax.bar_label(bars, fmt="%.2f", fontsize=13, fontweight="bold")
ax.annotate(
    f"-{sv_stat:.1f}%\nvs. static",
    (2, En[2]),
    textcoords="offset points",
    xytext=(0, 18),
    ha="center",
    fontsize=13,
    fontweight="bold",
    color="#217821",
)
ax.axhline(1.0, ls="--", color="#333", lw=1.6)
ax.set_xticks(range(3))
ax.set_xticklabels(names)
ax.set_ylim(0, max(En) * 1.2)
ax.set_ylabel("Normalized total NoC energy\n(w.r.t. Baseline)", fontsize=15)
for lb in ax.get_xticklabels() + ax.get_yticklabels():
    lb.set_fontweight("bold")
fig.tight_layout()
fig.savefig(f"{OUT}/F16_dsent_energy.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F16_dsent_energy.pdf")

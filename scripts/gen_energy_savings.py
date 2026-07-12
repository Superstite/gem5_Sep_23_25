#!/usr/bin/env python3
"""First-order express-link energy model + savings plot.

Express resources (2-hop link drivers, their input VCs/buffers, express crossbar
ports) are clock/power-gated when a router's express is inactive. First-order
model: express-link energy ~ (active express-link-epochs) x E_unit. Reactive
gates express (duty < 100%); static-all never does. Energy saving = the gated
fraction. Data: per-router per-epoch express state (ex) from the reactive real
MiBench run (ReconTrace), new VC layout.
"""
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "/home/sneha/Github_Repos/gem5_Sep_23_25"
OUT = f"{ROOT}/scripts/recon_results/summary"
LOG = f"{ROOT}/m5realv_react_duty/run.log"
RE = re.compile(r"RTRACE t=(\d+) R\d+ .* ex=(\d+)")

on = tot = 0
epochs = set()
for ln in open(LOG):
    m = RE.search(ln)
    if m:
        tot += 1
        epochs.add(int(m.group(1)))
        on += int(m.group(2))
n_ep = len(epochs)
routers = tot // n_ep  # 64
# active express-link-epochs (first-order energy proxy, E_unit = 1)
E_static = routers * n_ep  # always on
E_react = on  # only when active
duty = 100.0 * E_react / E_static
saving = 100.0 * (E_static - E_react) / E_static
print(
    f"epochs={n_ep} routers={routers}  static={E_static} react={E_react} "
    f"duty={duty:.1f}%  express-energy saving={saving:.1f}%"
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
fig, ax = plt.subplots(figsize=(6.4, 5.0))
vals = [1.0, E_react / E_static]
labels = ["Static (Always-ON)\nExpress", "Reactive\nExpress"]
cols = ["#1a53ff", "#2ca02c"]
bars = ax.bar(
    [0, 1],
    vals,
    0.5,
    color=cols,
    edgecolor="black",
    linewidth=1.2,
    hatch=["//", "\\\\"],
)
ax.bar_label(bars, fmt="%.2f", fontsize=14, fontweight="bold")
ax.annotate(
    f"-{saving:.0f}%\n(energy saved)",
    (1, vals[1]),
    textcoords="offset points",
    xytext=(0, 20),
    ha="center",
    fontsize=14,
    fontweight="bold",
    color="#217821",
)
# arrow showing the saved fraction
ax.annotate(
    "",
    xy=(1.32, vals[1]),
    xytext=(1.32, 1.0),
    arrowprops=dict(arrowstyle="<->", color="#217821", lw=2),
)
ax.text(
    1.37,
    (1.0 + vals[1]) / 2,
    f"{saving:.0f}% saved",
    rotation=90,
    va="center",
    fontsize=12,
    fontweight="bold",
    color="#217821",
)
ax.set_xticks([0, 1])
ax.set_xticklabels(labels)
ax.set_ylim(0, 1.2)
ax.set_ylabel(
    "Normalized express-link energy\n(active link-epochs)", fontsize=15
)
for lb in ax.get_xticklabels() + ax.get_yticklabels():
    lb.set_fontweight("bold")
fig.tight_layout()
fig.savefig(f"{OUT}/F15_energy_savings.pdf", bbox_inches="tight")
print(f"[done] -> {OUT}/F15_energy_savings.pdf")

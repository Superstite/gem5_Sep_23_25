#!/usr/bin/env python3
"""
IEEE system-architecture figures for the self-aware reconfigurable NoC.
Two STANDALONE figures:

  FIG_system_mesh : augmented 8x8 CustomMesh -- base XY mesh + dormant/active
                    two-hop express links, HC vs LC cores, MC/directory sinks.
  FIG_system_loop : self-aware reconfiguration loop (Sense -> Decide ->
                    Actuate) + router-tile detail (criticality-partitioned VCs).

Schematic only (no simulation data) -- illustrates the architecture in Sec. III.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import (
    FancyArrowPatch,
    FancyBboxPatch,
    Rectangle,
)

OUT = (
    "/home/sneha/Github_Repos/gem5_Sep_23_25/scripts/recon_results/motivation"
)

MESH = 8
HC_SRCS = {0, 3, 10, 20, 29, 35, 48, 59}
MC = {21, 42}

HC_C = "#2E86DE"  # HC = bold blue
LC_C = "#F2DE73"  # LC = yellowish
MC_C = "#C0501E"  # MC = rust
EXP_ON = "#159A46"
EXP_OFF = "#8E24AA"
BASE_C = "black"  # bold black base links
BOX_C = "#1565C0"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
    }
)


def rc(i):
    r, c = i // MESH, i % MESH
    return c, (MESH - 1 - r)


# ===========================================================================
# FIG (a) — Augmented mesh
# ===========================================================================
figa, axm = plt.subplots(figsize=(6.6, 6.6))
axm.set_aspect("equal")
axm.axis("off")
axm.set_xlim(-0.8, MESH - 0.2)
axm.set_ylim(-1.9, MESH - 0.2)

for i in range(64):
    x, y = rc(i)
    r, c = i // MESH, i % MESH
    if c < MESH - 1:
        axm.plot([x, x + 1], [y, y], color=BASE_C, lw=2.2, zorder=1)
    if r < MESH - 1:
        axm.plot([x, x], [y, y - 1], color=BASE_C, lw=2.2, zorder=1)


def express(a, b, color, style, lw):
    xa, ya = rc(a)
    xb, yb = rc(b)
    axm.add_patch(
        FancyArrowPatch(
            (xa, ya),
            (xb, yb),
            connectionstyle="arc3,rad=0.28",
            arrowstyle="-",
            lw=lw,
            color=color,
            linestyle=style,
            zorder=2,
        )
    )


express(19, 21, EXP_ON, "solid", 4.2)
express(37, 21, EXP_ON, "solid", 4.2)
express(26, 42, EXP_OFF, (0, (4, 3)), 3.4)
express(40, 42, EXP_OFF, (0, (4, 3)), 3.4)

for i in range(64):
    x, y = rc(i)
    if i in MC:
        axm.add_patch(
            Rectangle(
                (x - 0.34, y - 0.34),
                0.68,
                0.68,
                fc=MC_C,
                ec="black",
                lw=2.6,
                hatch="xxx",
                zorder=4,
            )
        )
        axm.text(
            x,
            y,
            "MC",
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color="white",
            zorder=5,
        )
        axm.text(
            x,
            y - 0.50,
            f"R{i}",
            ha="center",
            va="top",
            fontsize=8,
            color="black",
            fontweight="bold",
            zorder=5,
        )
    elif i in HC_SRCS:
        axm.add_patch(
            Rectangle(
                (x - 0.29, y - 0.29),
                0.58,
                0.58,
                fc=HC_C,
                ec="black",
                lw=2.4,
                hatch="----",
                zorder=4,
            )
        )
    else:
        axm.add_patch(
            Rectangle(
                (x - 0.25, y - 0.25),
                0.50,
                0.50,
                fc=LC_C,
                ec="black",
                lw=2.0,
                hatch="||||",
                zorder=3,
            )
        )

from matplotlib.patches import Patch

leg = [
    Patch(fc=HC_C, ec="black", lw=1.8, hatch="----", label="HC core (8)"),
    Patch(fc=LC_C, ec="black", lw=1.8, hatch="||||", label="LC core (56)"),
    Patch(
        fc=MC_C, ec="black", lw=1.8, hatch="xxx", label="MC / directory sink"
    ),
    Line2D([0], [0], color=EXP_ON, lw=4, label="express link – active"),
    Line2D(
        [0],
        [0],
        color=EXP_OFF,
        lw=3.4,
        ls="--",
        label="express link – dormant",
    ),
    Line2D([0], [0], color=BASE_C, lw=2.2, label="base XY link"),
]
axm.legend(
    handles=leg,
    loc="lower center",
    bbox_to_anchor=(0.5, -0.02),
    ncol=2,
    fontsize=11,
    framealpha=0.95,
    handlelength=1.8,
    columnspacing=1.3,
)

figa.tight_layout()
figa.savefig(f"{OUT}/FIG_system_mesh.pdf", bbox_inches="tight")
figa.savefig(f"{OUT}/FIG_system_mesh.png", dpi=200, bbox_inches="tight")
plt.close(figa)

# ===========================================================================
# FIG (b) — Self-aware reconfiguration loop + tile detail
# ===========================================================================
figb, axb = plt.subplots(figsize=(7.4, 6.2))
axb.set_xlim(0, 10)
axb.set_ylim(0, 10)
axb.axis("off")


def box(x, y, w, h, text, fc, ec=BOX_C, fs=10.5, tc="black"):
    axb.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.08,rounding_size=0.15",
            fc=fc,
            ec=ec,
            lw=2.0,
            zorder=3,
        )
    )
    axb.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        fontweight="bold",
        color=tc,
        zorder=4,
    )


def arrow(x0, y0, x1, y1, text=None, color=BOX_C, rad=0.0, tx=0, ty=0):
    axb.add_patch(
        FancyArrowPatch(
            (x0, y0),
            (x1, y1),
            arrowstyle="-|>",
            mutation_scale=20,
            lw=2.4,
            color=color,
            connectionstyle=f"arc3,rad={rad}",
            zorder=5,
        )
    )
    if text:
        axb.text(
            (x0 + x1) / 2 + tx,
            (y0 + y1) / 2 + ty,
            text,
            ha="center",
            va="center",
            fontsize=9.5,
            color=color,
            fontweight="bold",
        )


box(
    3.3,
    8.05,
    4.0,
    1.35,
    "SENSE\nper-router HC/LC flits,\nVC occupancy",
    fc="#E3F2FD",
    fs=10,
)
box(
    3.3,
    5.55,
    4.0,
    1.35,
    "DECIDE\nwatermark + policy\n(reactive HC-onset)",
    fc="#FFF3E0",
    fs=10,
)
box(
    3.3,
    3.05,
    4.0,
    1.35,
    "ACTUATE\nactivate express /\nelastic VC merge",
    fc="#E8F5E9",
    fs=10,
)

arrow(5.3, 8.05, 5.3, 6.90)
arrow(5.3, 5.55, 5.3, 4.40)

box(0.2, 5.55, 2.4, 1.35, "8×8 NoC\n(Garnet)", fc="#F3E5F5", fs=10)
arrow(
    3.3,
    3.55,
    1.4,
    5.55,
    text="reconfig\n(per epoch)",
    color=EXP_ON,
    rad=-0.3,
    tx=-0.25,
    ty=-0.2,
)
arrow(
    1.4,
    6.90,
    3.3,
    8.6,
    text="telemetry",
    color="#1565C0",
    rad=-0.3,
    tx=-0.4,
    ty=0.2,
)

axb.text(
    5.3,
    2.65,
    "epoch = 100 cycles",
    ha="center",
    va="center",
    fontsize=10,
    style="italic",
    color="#555",
)

# tile detail
ty0 = 0.2
axb.add_patch(
    FancyBboxPatch(
        (0.2, ty0),
        9.6,
        2.15,
        boxstyle="round,pad=0.05",
        fc="white",
        ec="#999",
        lw=1.6,
        zorder=1,
    )
)
axb.text(
    0.5,
    ty0 + 1.82,
    "Router tile",
    fontsize=10.5,
    fontweight="bold",
    ha="left",
    zorder=7,
)
box(0.6, ty0 + 0.40, 1.8, 1.0, "Core\n+ L1 I/D", fc="#ECEFF1", fs=9.5)
arrow(2.4, ty0 + 0.90, 3.0, ty0 + 0.90, color="#555")
rx = 3.1
axb.text(
    rx + 2.4,
    ty0 + 1.62,
    "Router: criticality-partitioned VCs",
    fontsize=9.5,
    fontweight="bold",
    ha="center",
    zorder=7,
)
for k, (lab, col) in enumerate(
    [("VC0", HC_C), ("VC1", HC_C), ("VC2", LC_C), ("VC3", LC_C)]
):
    bx = rx + 0.2 + k * 1.15
    axb.add_patch(
        Rectangle(
            (bx, ty0 + 0.50), 1.0, 0.8, fc=col, ec="black", lw=1.2, zorder=6
        )
    )
    tc = "white" if col == HC_C else "black"
    axb.text(
        bx + 0.5,
        ty0 + 0.90,
        lab,
        ha="center",
        va="center",
        fontsize=9,
        fontweight="bold",
        color=tc,
        zorder=7,
    )
axb.text(
    rx + 0.75,
    ty0 + 0.28,
    "HC (protected)",
    fontsize=8,
    color=HC_C,
    ha="center",
    fontweight="bold",
    zorder=7,
)
axb.text(
    rx + 3.05,
    ty0 + 0.28,
    "LC (donor, elastic)",
    fontsize=8,
    color="#555",
    ha="center",
    fontweight="bold",
    zorder=7,
)
box(
    8.3, ty0 + 0.40, 1.3, 1.0, "express\nport", fc="#E8F5E9", ec=EXP_ON, fs=8.5
)
arrow(8.0, ty0 + 0.90, 8.3, ty0 + 0.90, color=EXP_ON)

figb.tight_layout()
figb.savefig(f"{OUT}/FIG_system_loop.pdf", bbox_inches="tight")
figb.savefig(f"{OUT}/FIG_system_loop.png", dpi=200, bbox_inches="tight")
plt.close(figb)

print(f"[done] {OUT}/FIG_system_mesh.pdf + FIG_system_loop.pdf (+ .png)")

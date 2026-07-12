#!/usr/bin/env python3
"""
System figure (reference-style): the INFLUENTIAL ROUTER NODE.

An 8x8 mesh of router nodes; the routers connected to a memory-controller /
directory (R21, R42) are the *influential* nodes -- all memory traffic sinks
there, so their links dominate congestion. One influential node is called out
(red dashed) to a detail view showing its express/base links, its connection to
the Directory controller, and the Self-Aware Reconfiguration Manager that senses
the node and feeds back reconfiguration decisions.

Schematic only (no simulation data).
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import (
    FancyArrowPatch,
    FancyBboxPatch,
    Patch,
    Rectangle,
)

OUT = (
    "/home/sneha/Github_Repos/gem5_Sep_23_25/scripts/recon_results/motivation"
)
MESH = 8
MC = {21, 42}
CALLOUT = 42  # influential node shown in the detail view

NODE_C = "#9DB8E0"  # other router nodes (blue)
INF_C = "#F4B183"  # influential (MC-connected) node (orange)
DIR_C = "white"
MOD_C = "#A9D18E"  # reconfiguration module (green)
FB_C = "#E00000"  # feedback (red)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.weight": "bold",
        "axes.labelweight": "bold",
    }
)

fig, ax = plt.subplots(figsize=(14.6, 6.8))
ax.set_xlim(-0.8, 16.0)
ax.set_ylim(-1.6, 8.2)
ax.set_aspect("equal")
ax.axis("off")


def rc(i):
    r, c = i // MESH, i % MESH
    return c, (MESH - 1 - r)


# ---- base links: dashed; links touching an MC node are solid+bold ----------
for i in range(64):
    x, y = rc(i)
    r, c = i // MESH, i % MESH
    for j, (nx, ny) in (
        ((i + 1), (x + 1, y)) if c < MESH - 1 else (None, (0, 0))
    ), (((i + MESH), (x, y - 1)) if r < MESH - 1 else (None, (0, 0))):
        if j is None:
            continue
        solid = (i in MC) or (j in MC)
        ax.plot(
            [x, nx],
            [y, ny],
            color="black",
            lw=2.6 if solid else 1.1,
            ls="solid" if solid else (0, (4, 3)),
            zorder=1,
        )


def draw_node(x, y, influential):
    w, h = 0.52, 0.46
    fc = INF_C if influential else NODE_C
    hatch = "///" if influential else None
    ax.add_patch(
        Rectangle(
            (x - w / 2, y - h / 2),
            w,
            h,
            fc=fc,
            ec="black",
            lw=2.0,
            hatch=hatch,
            zorder=4,
        )
    )
    # two-cell look: internal vertical divider
    ax.plot([x, x], [y - h / 2, y + h / 2], color="black", lw=1.2, zorder=5)


for i in range(64):
    x, y = rc(i)
    draw_node(x, y, i in MC)

# ---- callout of the influential node ---------------------------------------
cx, cy = rc(CALLOUT)
# detail box (compact)
BX, BY, BW, BH = 8.5, 2.8, 1.95, 1.7
ax.add_patch(
    Rectangle(
        (BX, BY), BW, BH, fc=INF_C, ec="black", lw=2.4, hatch="///", zorder=4
    )
)
ax.add_patch(
    Rectangle((BX, BY), BW, BH, fc="none", ec="black", lw=2.4, zorder=6)
)
ax.text(
    BX + BW / 2,
    BY + BH / 2,
    "Influential\nRouter node\n(MC-connected)",
    ha="center",
    va="center",
    fontsize=11,
    fontweight="bold",
    zorder=7,
)

# red dashed leader lines from the mesh node to the detail box
for (mx, my), (tx, ty) in [
    ((cx + 0.26, cy + 0.23), (BX, BY + BH)),
    ((cx + 0.26, cy - 0.23), (BX, BY)),
]:
    ax.add_patch(
        FancyArrowPatch(
            (mx, my),
            (tx, ty),
            arrowstyle="-",
            color=FB_C,
            lw=2.0,
            ls=(0, (5, 3)),
            zorder=3,
        )
    )


# directed express/base links out of the detail box
def link(x0, y0, x1, y1, style, label, lx, ly, rot=0):
    ax.add_patch(
        FancyArrowPatch(
            (x0, y0),
            (x1, y1),
            arrowstyle="-|>",
            mutation_scale=18,
            lw=2.6,
            color="black",
            ls=style,
            zorder=3,
        )
    )
    ax.text(
        lx,
        ly,
        label,
        ha="center",
        va="center",
        fontsize=9.5,
        fontweight="bold",
        rotation=rot,
    )


# up (active express) and down (base) only -- keep the right side clear for
# the control-plane boxes
link(
    BX + BW / 2,
    BY + BH,
    BX + BW / 2,
    BY + BH + 1.05,
    "solid",
    "express\n(active)",
    BX + BW / 2 - 0.62,
    BY + BH + 0.55,
)
link(
    BX + BW / 2,
    BY,
    BX + BW / 2,
    BY - 1.05,
    (0, (4, 3)),
    "base link",
    BX + BW / 2 - 0.55,
    BY - 0.55,
)
# a short right express stub + incoming dashed, both stop well before the boxes
link(
    BX + BW,
    BY + BH - 0.35,
    BX + BW + 0.7,
    BY + BH - 0.35,
    "solid",
    "express",
    BX + BW + 0.35,
    BY + BH - 0.05,
)
ax.add_patch(
    FancyArrowPatch(
        (BX + BW + 0.7, BY + 0.3),
        (BX + BW, BY + 0.3),
        arrowstyle="-|>",
        mutation_scale=18,
        lw=2.6,
        color="black",
        ls=(0, (4, 3)),
        zorder=3,
    )
)

# ---- Directory controller + Reconfiguration Manager + feedback -------------
DX, DY, DW, DH = 12.1, 5.9, 2.7, 1.6
ax.add_patch(
    FancyBboxPatch(
        (DX, DY),
        DW,
        DH,
        boxstyle="round,pad=0.05",
        fc=DIR_C,
        ec="black",
        lw=2.4,
        zorder=5,
    )
)
ax.text(
    DX + DW / 2,
    DY + DH / 2,
    "Directory\ncontroller (MC)",
    ha="center",
    va="center",
    fontsize=12.5,
    fontweight="bold",
    zorder=6,
)

MXX, MYY, MWW, MHH = 12.1, 3.9, 3.0, 1.4
ax.add_patch(
    FancyBboxPatch(
        (MXX, MYY),
        MWW,
        MHH,
        boxstyle="round,pad=0.08,rounding_size=0.25",
        fc=MOD_C,
        ec="black",
        lw=2.2,
        zorder=5,
    )
)
ax.text(
    MXX + MWW / 2,
    MYY + MHH / 2,
    "Self-Aware\nReconfiguration\nManager",
    ha="center",
    va="center",
    fontsize=11,
    fontweight="bold",
    zorder=6,
)

# thick arrow: influential node -> directory controller
ax.add_patch(
    FancyArrowPatch(
        (BX + BW, BY + BH),
        (DX, DY + 0.25),
        arrowstyle="-|>",
        mutation_scale=26,
        lw=6,
        color="black",
        zorder=3,
    )
)
# sense: influential node -> manager (thin, low arc)
ax.add_patch(
    FancyArrowPatch(
        (BX + BW, BY + 0.5),
        (MXX, MYY + 0.45),
        arrowstyle="-|>",
        mutation_scale=16,
        lw=2.2,
        color="#333",
        connectionstyle="arc3,rad=0.18",
        zorder=2,
    )
)
ax.text(
    (BX + BW + MXX) / 2,
    BY - 0.15,
    "sense",
    color="#333",
    fontsize=10,
    fontweight="bold",
    ha="center",
)
# feedback: manager -> directory controller (red), around the right side
ax.add_patch(
    FancyArrowPatch(
        (MXX + MWW, MYY + MHH * 0.7),
        (DX + DW, DY + 0.3),
        arrowstyle="-|>",
        mutation_scale=20,
        lw=3.2,
        color=FB_C,
        connectionstyle="arc3,rad=-0.55",
        zorder=3,
    )
)
ax.text(
    DX + DW + 0.75,
    DY - 0.15,
    "Feedback",
    color=FB_C,
    fontsize=11,
    fontweight="bold",
    ha="center",
)

# ---- legend ----------------------------------------------------------------
leg = [
    Patch(
        fc=INF_C,
        ec="black",
        hatch="///",
        label="Router node connected to a\nmemory controller (influential)",
    ),
    Patch(fc=NODE_C, ec="black", label="Other router nodes"),
    Line2D([0], [0], color="black", lw=2.6, label="MC-incident link (solid)"),
    Line2D(
        [0], [0], color="black", lw=1.2, ls="--", label="base XY link (dashed)"
    ),
]
ax.legend(
    handles=leg,
    loc="lower right",
    bbox_to_anchor=(1.0, -0.02),
    fontsize=10.5,
    framealpha=0.97,
    handlelength=1.8,
    borderpad=0.8,
    labelspacing=0.7,
)

fig.savefig(f"{OUT}/FIG_influential_router.pdf", bbox_inches="tight")
fig.savefig(f"{OUT}/FIG_influential_router.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"[done] {OUT}/FIG_influential_router.pdf / .png")

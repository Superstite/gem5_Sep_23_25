#!/usr/bin/env python3
"""
Run and analyze Garnet experiments that test whether network instability
originates near memory controllers.

The experiment moves the two memory-side controller routers, runs the existing
MiBench multi-program workload config, and checks whether router activity and
traffic hot spots follow those controller locations.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from statistics import (
    mean,
    pstdev,
)

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = (
    REPO_ROOT
    / "configs/network/network_config_sneha_executing_all_benchmarks.py"
)
NETWORK_PREFIX = "board.cache_hierarchy.ruby_system.network"


@dataclass(frozen=True)
class RunSpec:
    name: str
    cores: int
    rows: int
    cols: int
    first_dir: int
    second_dir: int
    routing_algorithm: int
    run_dir: Path

    @property
    def controller_routers(self) -> tuple[int, int]:
        return (self.first_dir, self.second_dir)


def parse_controller_pair(raw: str) -> tuple[int, int]:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(
            f"controller pair '{raw}' must look like FIRST,SECOND"
        )
    return int(parts[0]), int(parts[1])


def stat_value(line: str) -> float | None:
    fields = line.split()
    if len(fields) < 2:
        return None
    try:
        return float(fields[1])
    except ValueError:
        return None


def read_stats(path: Path) -> dict[str, float]:
    stats: dict[str, float] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("-") or line.startswith("Begin "):
                continue
            fields = line.split()
            if len(fields) < 2:
                continue
            value = stat_value(line)
            if value is not None and math.isfinite(value):
                stats[fields[0]] = value
    return stats


def read_stat_vectors(path: Path) -> dict[str, list[float]]:
    vectors: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            fields = line.split()
            if len(fields) < 2 or "|" not in line:
                continue
            values: list[float] = []
            for raw in re.findall(r"\|\s*([-+0-9.eEnNaAfFiI.]+)", line):
                try:
                    value = float(raw)
                except ValueError:
                    continue
                if math.isfinite(value):
                    values.append(value)
            if values:
                vectors[fields[0]] = values
    return vectors


def router_xy(router: int, cols: int) -> tuple[int, int]:
    return router % cols, router // cols


def manhattan(a: int, b: int, cols: int) -> int:
    ax, ay = router_xy(a, cols)
    bx, by = router_xy(b, cols)
    return abs(ax - bx) + abs(ay - by)


def nearest_controller_distance(
    router: int, controllers: tuple[int, int], cols: int
) -> int:
    return min(
        manhattan(router, controller, cols) for controller in controllers
    )


def parse_traffic(
    stats: dict[str, float], kind: str
) -> dict[tuple[int, int], float]:
    pattern = re.compile(
        rf"^{re.escape(NETWORK_PREFIX)}\.{kind}_traffic_distribution\.n(\d+)\.n(\d+)$"
    )
    traffic: dict[tuple[int, int], float] = {}
    for key, value in stats.items():
        match = pattern.match(key)
        if match:
            src = int(match.group(1))
            dst = int(match.group(2))
            traffic[(src, dst)] = value
    return traffic


def parse_router_activity(
    stats: dict[str, float],
) -> dict[int, dict[str, float]]:
    pattern = re.compile(
        rf"^{re.escape(NETWORK_PREFIX)}\.routers0?(\d+)\."
        r"(buffer_reads|buffer_writes|crossbar_activity|"
        r"sw_input_arbiter_activity|sw_output_arbiter_activity)$"
    )
    routers: dict[int, dict[str, float]] = {}
    for key, value in stats.items():
        match = pattern.match(key)
        if match:
            router = int(match.group(1))
            metric = match.group(2)
            routers.setdefault(router, {})[metric] = value
    return routers


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mx = mean(xs)
    my = mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return numerator / (denom_x * denom_y)


def router_rows(
    spec: RunSpec, stats: dict[str, float]
) -> list[dict[str, object]]:
    data_traffic = parse_traffic(stats, "data")
    ctrl_traffic = parse_traffic(stats, "ctrl")
    router_activity = parse_router_activity(stats)
    routers = set(range(spec.cores))
    routers.update(router_activity.keys())
    for src, dst in list(data_traffic) + list(ctrl_traffic):
        routers.add(src)
        routers.add(dst)

    rows: list[dict[str, object]] = []
    for router in sorted(routers):
        inbound_data = sum(
            value
            for (src, dst), value in data_traffic.items()
            if dst == router
        )
        outbound_data = sum(
            value
            for (src, dst), value in data_traffic.items()
            if src == router
        )
        inbound_ctrl = sum(
            value
            for (src, dst), value in ctrl_traffic.items()
            if dst == router
        )
        outbound_ctrl = sum(
            value
            for (src, dst), value in ctrl_traffic.items()
            if src == router
        )
        activity = router_activity.get(router, {})
        distance = nearest_controller_distance(
            router, spec.controller_routers, spec.cols
        )
        rows.append(
            {
                "run": spec.name,
                "cores": spec.cores,
                "rows": spec.rows,
                "cols": spec.cols,
                "first_dir": spec.first_dir,
                "second_dir": spec.second_dir,
                "routing_algorithm": spec.routing_algorithm,
                "router": router,
                "x": router_xy(router, spec.cols)[0],
                "y": router_xy(router, spec.cols)[1],
                "distance_to_controller": distance,
                "near_controller": int(distance <= 1),
                "data_inbound": inbound_data,
                "data_outbound": outbound_data,
                "ctrl_inbound": inbound_ctrl,
                "ctrl_outbound": outbound_ctrl,
                "total_inbound": inbound_data + inbound_ctrl,
                "total_outbound": outbound_data + outbound_ctrl,
                "total_traffic": inbound_data
                + inbound_ctrl
                + outbound_data
                + outbound_ctrl,
                "buffer_reads": activity.get("buffer_reads", 0.0),
                "buffer_writes": activity.get("buffer_writes", 0.0),
                "crossbar_activity": activity.get("crossbar_activity", 0.0),
                "sw_input_arbiter_activity": activity.get(
                    "sw_input_arbiter_activity", 0.0
                ),
                "sw_output_arbiter_activity": activity.get(
                    "sw_output_arbiter_activity", 0.0
                ),
            }
        )
    return rows


def summarize_run(
    spec: RunSpec,
    rows: list[dict[str, object]],
    stats: dict[str, float],
    vectors: dict[str, list[float]],
) -> dict[str, object]:
    near = [row for row in rows if int(row["near_controller"])]
    far = [row for row in rows if not int(row["near_controller"])]

    def avg(group: list[dict[str, object]], metric: str) -> float:
        return mean(float(row[metric]) for row in group) if group else 0.0

    def sd(group: list[dict[str, object]], metric: str) -> float:
        return (
            pstdev(float(row[metric]) for row in group)
            if len(group) > 1
            else 0.0
        )

    def vector_sd(stat_name: str) -> float:
        values = vectors.get(f"{NETWORK_PREFIX}.{stat_name}", [])
        return pstdev(values) if len(values) > 1 else 0.0

    distances = [float(row["distance_to_controller"]) for row in rows]
    buffer_reads = [float(row["buffer_reads"]) for row in rows]
    total_traffic = [float(row["total_traffic"]) for row in rows]
    hottest = max(rows, key=lambda row: float(row["buffer_reads"]))
    traffic_hottest = max(rows, key=lambda row: float(row["total_traffic"]))

    return {
        "run": spec.name,
        "cores": spec.cores,
        "rows": spec.rows,
        "cols": spec.cols,
        "first_dir": spec.first_dir,
        "second_dir": spec.second_dir,
        "routing_algorithm": spec.routing_algorithm,
        "avg_packet_latency": stats.get(
            f"{NETWORK_PREFIX}.average_packet_latency", 0.0
        ),
        "avg_packet_queueing_latency": stats.get(
            f"{NETWORK_PREFIX}.average_packet_queueing_latency", 0.0
        ),
        "avg_flit_latency": stats.get(
            f"{NETWORK_PREFIX}.average_flit_latency", 0.0
        ),
        "avg_flit_queueing_latency": stats.get(
            f"{NETWORK_PREFIX}.average_flit_queueing_latency", 0.0
        ),
        "packet_vnet_latency_stdev": vector_sd("average_packet_vnet_latency"),
        "packet_vqueue_latency_stdev": vector_sd(
            "average_packet_vqueue_latency"
        ),
        "flit_vnet_latency_stdev": vector_sd("average_flit_vnet_latency"),
        "flit_vqueue_latency_stdev": vector_sd("average_flit_vqueue_latency"),
        "near_avg_buffer_reads": avg(near, "buffer_reads"),
        "far_avg_buffer_reads": avg(far, "buffer_reads"),
        "near_buffer_read_stdev": sd(near, "buffer_reads"),
        "far_buffer_read_stdev": sd(far, "buffer_reads"),
        "near_avg_total_traffic": avg(near, "total_traffic"),
        "far_avg_total_traffic": avg(far, "total_traffic"),
        "near_total_traffic_stdev": sd(near, "total_traffic"),
        "far_total_traffic_stdev": sd(far, "total_traffic"),
        "distance_buffer_read_corr": pearson(distances, buffer_reads),
        "distance_total_traffic_corr": pearson(distances, total_traffic),
        "hottest_activity_router": hottest["router"],
        "hottest_activity_router_distance": hottest["distance_to_controller"],
        "hottest_traffic_router": traffic_hottest["router"],
        "hottest_traffic_router_distance": traffic_hottest[
            "distance_to_controller"
        ],
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_gem5(
    spec: RunSpec,
    gem5_binary: Path,
    config: Path,
    extra_gem5_args: list[str],
    max_ticks: int,
    initialize_only: bool,
) -> None:
    spec.run_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(gem5_binary),
        "-d",
        str(spec.run_dir),
        *extra_gem5_args,
        str(config),
        str(spec.cores),
        "--routing-algorithm",
        str(spec.routing_algorithm),
        "--num-rows",
        str(spec.rows),
        "--num-cols",
        str(spec.cols),
        "--first-dir-loc",
        str(spec.first_dir),
        "--second-dir-loc",
        str(spec.second_dir),
        "--max-ticks",
        str(max_ticks),
    ]
    if initialize_only:
        cmd.append("--initialize-only")
    print("Running:", " ".join(cmd), flush=True)
    with (spec.run_dir / "command.txt").open("w", encoding="utf-8") as handle:
        handle.write(" ".join(cmd) + "\n")
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def plot_results(out_dir: Path, router_csv: Path, summary_csv: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed; CSV outputs are still available.")
        return

    with router_csv.open("r", encoding="utf-8") as handle:
        router_rows_data = list(csv.DictReader(handle))
    with summary_csv.open("r", encoding="utf-8") as handle:
        summary_rows = list(csv.DictReader(handle))

    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    for run_name in sorted({row["run"] for row in router_rows_data}):
        run_rows = [row for row in router_rows_data if row["run"] == run_name]
        cols = max(int(row["x"]) for row in run_rows) + 1
        rows = max(int(row["y"]) for row in run_rows) + 1
        heat = [[0.0 for _ in range(cols)] for _ in range(rows)]
        for row in run_rows:
            heat[int(row["y"])][int(row["x"])] = float(row["buffer_reads"])

        plt.figure(figsize=(7, 6))
        plt.imshow(heat, cmap="magma", origin="upper")
        plt.colorbar(label="router buffer reads")
        controllers = [
            int(run_rows[0]["first_dir"]),
            int(run_rows[0]["second_dir"]),
        ]
        for controller in controllers:
            x, y = router_xy(controller, cols)
            plt.scatter([x], [y], marker="x", s=120, c="cyan", linewidths=3)
        plt.title(f"{run_name}: router activity heatmap")
        plt.xlabel("mesh x")
        plt.ylabel("mesh y")
        plt.tight_layout()
        plt.savefig(
            fig_dir / f"{run_name}_router_activity_heatmap.png", dpi=180
        )
        plt.close()

    labels = [row["run"] for row in summary_rows]
    near_vals = [float(row["near_avg_buffer_reads"]) for row in summary_rows]
    far_vals = [float(row["far_avg_buffer_reads"]) for row in summary_rows]
    xs = range(len(labels))
    plt.figure(figsize=(max(8, len(labels) * 1.3), 5))
    plt.bar([x - 0.2 for x in xs], near_vals, width=0.4, label="near MC")
    plt.bar([x + 0.2 for x in xs], far_vals, width=0.4, label="far from MC")
    plt.xticks(list(xs), labels, rotation=30, ha="right")
    plt.ylabel("average router buffer reads")
    plt.title("Near-controller routers vs far routers")
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "near_vs_far_buffer_reads.png", dpi=180)
    plt.close()

    correlations = [
        float(row["distance_buffer_read_corr"]) for row in summary_rows
    ]
    plt.figure(figsize=(max(8, len(labels) * 1.3), 4))
    plt.axhline(0, color="black", linewidth=1)
    plt.bar(labels, correlations, color="#4677c9")
    plt.xticks(rotation=30, ha="right")
    plt.ylabel("Pearson corr(distance to MC, buffer reads)")
    plt.title("Negative values mean activity concentrates near controllers")
    plt.tight_layout()
    plt.savefig(fig_dir / "distance_activity_correlation.png", dpi=180)
    plt.close()


def build_specs(args: argparse.Namespace) -> list[RunSpec]:
    specs: list[RunSpec] = []
    for cores in args.core_counts:
        rows = args.num_rows or math.isqrt(cores)
        cols = args.num_cols or cores // rows
        if rows * cols != cores:
            raise ValueError(f"{cores} cores cannot form {rows}x{cols} mesh")
        for first, second in args.controller_pairs:
            name = f"c{cores}_mc{first}_{second}_ra{args.routing_algorithm}"
            specs.append(
                RunSpec(
                    name=name,
                    cores=cores,
                    rows=rows,
                    cols=cols,
                    first_dir=first,
                    second_dir=second,
                    routing_algorithm=args.routing_algorithm,
                    run_dir=args.out_dir / "runs" / name,
                )
            )
    return specs


def analyze_specs(specs: list[RunSpec], out_dir: Path) -> None:
    all_router_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for spec in specs:
        stats_path = spec.run_dir / "stats.txt"
        if not stats_path.exists():
            print(f"Skipping {spec.name}: missing {stats_path}")
            continue
        stats = read_stats(stats_path)
        vectors = read_stat_vectors(stats_path)
        rows = router_rows(spec, stats)
        all_router_rows.extend(rows)
        summaries.append(summarize_run(spec, rows, stats, vectors))

    write_csv(out_dir / "router_metrics.csv", all_router_rows)
    write_csv(out_dir / "summary.csv", summaries)
    if summaries:
        print(f"Wrote {out_dir / 'summary.csv'}")
        print(f"Wrote {out_dir / 'router_metrics.csv'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("run", "analyze", "plot", "all"),
        default="analyze",
    )
    parser.add_argument(
        "--gem5-binary",
        type=Path,
        default=REPO_ROOT / "build/X86_MESI_Two_Level/gem5.debug",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "results/memory_controller_instability",
    )
    parser.add_argument(
        "--core-counts",
        type=int,
        nargs="+",
        default=[64],
        help="Core counts to run; 64 matches the default 8x8 mesh.",
    )
    parser.add_argument("--num-rows", type=int, default=8)
    parser.add_argument("--num-cols", type=int, default=8)
    parser.add_argument("--routing-algorithm", type=int, default=1)
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=1000000,
        help=(
            "Early stop tick passed to the benchmark config. "
            "The default is a smoke run, not a full simulation."
        ),
    )
    parser.add_argument(
        "--initialize-only",
        action="store_true",
        help=(
            "Instantiate gem5, dump stats, and exit without simulated ticks. "
            "Useful for checking that result creation works."
        ),
    )
    parser.add_argument(
        "--controller-pairs",
        type=parse_controller_pair,
        nargs="+",
        default=[
            (21, 42),
            (0, 63),
            (7, 56),
            (27, 36),
        ],
        help="Pairs like '21,42'. Moving hot spots with these pairs is causal evidence.",
    )
    parser.add_argument(
        "--extra-gem5-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Arguments inserted before the config path, for example --debug-flags.",
    )
    args = parser.parse_args()
    args.out_dir = args.out_dir.resolve()

    specs = build_specs(args)
    if args.mode in ("run", "all"):
        for spec in specs:
            run_gem5(
                spec,
                args.gem5_binary,
                args.config,
                args.extra_gem5_args,
                args.max_ticks,
                args.initialize_only,
            )
    if args.mode in ("analyze", "all"):
        analyze_specs(specs, args.out_dir)
    if args.mode in ("plot", "all"):
        plot_results(
            args.out_dir,
            args.out_dir / "router_metrics.csv",
            args.out_dir / "summary.csv",
        )


if __name__ == "__main__":
    main()

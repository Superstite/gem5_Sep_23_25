#!/usr/bin/env python3
"""Phase 0 MCS baseline sweep.

Establishes the reference behaviour the fuzzer must later beat:
  * how high-criticality (HC) flow latency degrades as low-criticality (LC)
    background load rises, for a fixed config, and
  * the standard synthetic-traffic DSE baseline.

For every run it stores full config + parsed metrics in a SQLite database so
the experiment is reproducible and queryable. This is the outer harness on top
of orchestrator.run() + stats_parser.

Usage:
    python3 tools/fuzzer/baseline_sweep.py [--quick]

See plans/mcs_trace_flow_plan.md (Phase 0).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3

from orchestrator import (
    REPO_ROOT,
    RunConfig,
    run,
)
from stats_parser import (
    criticality_summary,
    network_summary,
    parse_stats,
)

EXP_ROOT = os.path.join(REPO_ROOT, "experiments", "mcs_noc")
RUNS_DIR = os.path.join(EXP_ROOT, "runs")
DB_PATH = os.path.join(EXP_ROOT, "results.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT,
    git_hash TEXT,
    returncode INTEGER,
    wall_seconds REAL,
    topology TEXT,
    mesh_rows INTEGER,
    vcs_per_vnet INTEGER,
    routing_algorithm INTEGER,
    synthetic TEXT,
    injectionrate REAL,
    sim_cycles INTEGER,
    enable_criticality INTEGER,
    high_criticality_nis TEXT,
    -- aggregate metrics
    avg_packet_latency REAL,
    avg_flit_latency REAL,
    avg_hops REAL,
    flits_received_total REAL,
    avg_link_utilization REAL,
    -- per-criticality metrics
    hc_avg_packet_latency REAL,
    lc_avg_packet_latency REAL,
    hc_avg_flit_latency REAL,
    lc_avg_flit_latency REAL,
    hc_packets_received REAL,
    lc_packets_received REAL,
    config_json TEXT
);
"""


def init_db(path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def record(con: sqlite3.Connection, cfg: RunConfig, meta: dict) -> dict:
    agg, crit = {}, {}
    if meta["returncode"] == 0 and os.path.isfile(meta["stats_path"]):
        s = parse_stats(meta["stats_path"])
        agg = network_summary(s)
        crit = criticality_summary(s)
    con.execute(
        """INSERT INTO runs (
            tag, git_hash, returncode, wall_seconds, topology, mesh_rows,
            vcs_per_vnet, routing_algorithm, synthetic, injectionrate,
            sim_cycles, enable_criticality, high_criticality_nis,
            avg_packet_latency, avg_flit_latency, avg_hops,
            flits_received_total, avg_link_utilization,
            hc_avg_packet_latency, lc_avg_packet_latency,
            hc_avg_flit_latency, lc_avg_flit_latency,
            hc_packets_received, lc_packets_received, config_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            meta["tag"],
            meta["git_hash"],
            meta["returncode"],
            meta["wall_seconds"],
            cfg.topology,
            cfg.mesh_rows,
            cfg.vcs_per_vnet,
            cfg.routing_algorithm,
            cfg.synthetic,
            cfg.injectionrate,
            cfg.sim_cycles,
            int(cfg.enable_criticality),
            ",".join(str(x) for x in cfg.high_criticality_nis),
            agg.get("avg_packet_latency"),
            agg.get("avg_flit_latency"),
            agg.get("avg_hops"),
            agg.get("flits_received_total"),
            agg.get("avg_link_utilization"),
            crit.get("hc_avg_packet_latency"),
            crit.get("lc_avg_packet_latency"),
            crit.get("hc_avg_flit_latency"),
            crit.get("lc_avg_flit_latency"),
            crit.get("hc_packets_received"),
            crit.get("lc_packets_received"),
            json.dumps(meta["config"]),
        ),
    )
    con.commit()
    return {**agg, **crit}


# safety experiment
# Question: how bad does HC flow latency get as LC background load rises? → the eWCL baseline curve
def hc_under_lc_sweep(con, rates, sim_cycles, hc_nis):
    """Fixed config, HC nodes tagged, sweep LC background injection rate.
    Core Phase-0 experiment: HC latency vs offered load."""
    rows = []
    for r in rates:
        cfg = RunConfig(
            label="hc_under_lc",
            synthetic="uniform_random",
            injectionrate=r,
            sim_cycles=sim_cycles,
            enable_criticality=True,
            high_criticality_nis=hc_nis,
        )
        meta = run(cfg, RUNS_DIR)
        m = record(con, cfg, meta)
        rows.append((r, m))
        print(
            f"  inj={r:<5} rc={meta['returncode']} "
            f"HC_pkt_lat={_f(m.get('hc_avg_packet_latency'))} "
            f"LC_pkt_lat={_f(m.get('lc_avg_packet_latency'))} "
            f"HC_pkts={_f(m.get('hc_packets_received'))}"
        )
    return rows


# design-space experiment
def dse_baseline_sweep(con, patterns, configs, rate, sim_cycles):
    """Standard synthetic DSE baseline: pattern x config grid."""
    for pat in patterns:
        for c in configs:
            cfg = RunConfig(
                label="dse",
                synthetic=pat,
                injectionrate=rate,
                sim_cycles=sim_cycles,
                vcs_per_vnet=c["vcs"],
                routing_algorithm=c["ra"],
            )
            meta = run(cfg, RUNS_DIR)
            m = record(con, cfg, meta)
            print(
                f"  {pat:<16} vc={c['vcs']} ra={c['ra']} "
                f"rc={meta['returncode']} "
                f"pkt_lat={_f(m.get('avg_packet_latency'))}"
            )


def _f(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "  -  "
    return f"{x:.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--quick", action="store_true", help="tiny grid for a fast smoke check"
    )
    args = ap.parse_args()

    con = init_db()

    # NOTE: GarnetSyntheticTraffic compares curTick() (ticks) against
    # --sim-cycles, and the tester clock is ~1000 ticks/cycle, so sim_cycles
    # is effectively in ticks. Use millions to get a populated network.
    if args.quick:
        rates = [0.1, 0.3]
        sim_cycles = 2_000_000
        patterns = ["uniform_random"]
        configs = [{"vcs": 4, "ra": 1}]
    else:
        rates = [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]
        sim_cycles = 5_000_000
        patterns = [
            "uniform_random",
            "transpose",
            "bit_complement",
            "shuffle",
            "tornado",
        ]
        configs = [
            {"vcs": 2, "ra": 1},
            {"vcs": 4, "ra": 1},
            {"vcs": 8, "ra": 1},
            {"vcs": 4, "ra": 0},
        ]

    print("=== HC-under-LC sweep (HC NIs = corners 0,3,12,15) ===")
    hc_under_lc_sweep(con, rates, sim_cycles, hc_nis=[0, 3, 12, 15])

    print("=== DSE synthetic baseline ===")
    dse_baseline_sweep(con, patterns, configs, rate=0.2, sim_cycles=sim_cycles)

    n = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    print(f"\nStored {n} runs in {DB_PATH}")
    con.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Phase 0 run orchestrator for the mixed-criticality NoC study.

Launches a single gem5/Garnet synthetic-traffic run from a structured
RunConfig, captures full provenance (command line, git hash, stdout/stderr,
raw stats.txt), and returns a metadata dict. No simulator internals here --
everything is driven through the verified command-line interface.

See plans/mcs_trace_flow_plan.md (Phase 0).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import (
    asdict,
    dataclass,
    field,
)

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
DEFAULT_GEM5 = os.path.join(REPO_ROOT, "build", "NULL", "gem5.opt")
DEFAULT_SCRIPT = os.path.join(
    REPO_ROOT, "configs", "example", "garnet_synth_traffic.py"
)


@dataclass
class RunConfig:
    """One gem5 Garnet run. Fields map directly to verified CLI flags."""

    # Topology / network
    topology: str = "Mesh_XY"
    mesh_rows: int = 4
    num_cpus: int = 16
    num_dirs: int = 16
    vcs_per_vnet: int = 4
    routing_algorithm: int = 1  # 0 table, 1 XY, 2 custom
    link_latency: int = 1
    router_latency: int = 1

    # Traffic
    synthetic: str = "uniform_random"
    injectionrate: float = 0.1
    sim_cycles: int = 10000
    inj_vnet: int = -1  # -1 == any
    single_sender: int = -1  # -1 == all nodes inject
    single_dest: int = -1  # -1 == pattern-defined dest
    num_packets_max: int = -1

    # Mixed-criticality
    enable_criticality: bool = False
    high_criticality_nis: list[int] = field(default_factory=list)

    # Bookkeeping
    label: str = ""
    extra_args: list[str] = field(default_factory=list)

    def tag(self) -> str:
        """Short stable identifier for this config (used as run-dir name)."""
        hc = "-".join(str(x) for x in self.high_criticality_nis) or "none"
        return (
            f"{self.label or 'run'}_{self.topology}_r{self.mesh_rows}"
            f"_{self.synthetic}_inj{self.injectionrate:g}"
            f"_vc{self.vcs_per_vnet}_ra{self.routing_algorithm}"
            f"_crit{int(self.enable_criticality)}_hc{hc}"
        )


def build_argv(cfg: RunConfig, run_dir: str, gem5_bin: str, script: str):
    argv = [
        gem5_bin,
        "-d",
        run_dir,
        script,
        "--network=garnet",
        f"--topology={cfg.topology}",
        f"--mesh-rows={cfg.mesh_rows}",
        f"--num-cpus={cfg.num_cpus}",
        f"--num-dirs={cfg.num_dirs}",
        f"--vcs-per-vnet={cfg.vcs_per_vnet}",
        f"--routing-algorithm={cfg.routing_algorithm}",
        f"--link-latency={cfg.link_latency}",
        f"--router-latency={cfg.router_latency}",
        f"--synthetic={cfg.synthetic}",
        f"--injectionrate={cfg.injectionrate}",
        f"--sim-cycles={cfg.sim_cycles}",
    ]
    if cfg.inj_vnet >= 0:
        argv.append(f"--inj-vnet={cfg.inj_vnet}")
    if cfg.single_sender >= 0:
        argv.append(f"--single-sender-id={cfg.single_sender}")
    if cfg.single_dest >= 0:
        argv.append(f"--single-dest-id={cfg.single_dest}")
    if cfg.num_packets_max >= 0:
        argv.append(f"--num-packets-max={cfg.num_packets_max}")
    if cfg.enable_criticality:
        argv.append("--enable-criticality")
        if cfg.high_criticality_nis:
            nis = ",".join(str(x) for x in cfg.high_criticality_nis)
            argv.append(f"--high-criticality-nis={nis}")
    argv.extend(cfg.extra_args)
    return argv


def git_hash() -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", REPO_ROOT, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def run(
    cfg: RunConfig,
    run_root: str,
    gem5_bin: str = DEFAULT_GEM5,
    script: str = DEFAULT_SCRIPT,
    timeout: int = 1800,
) -> dict:
    """Execute one run. Returns metadata dict; raises nothing on sim failure
    (returncode is captured so a sweep can continue)."""
    if not os.path.isfile(gem5_bin):
        raise FileNotFoundError(f"gem5 binary not found: {gem5_bin}")

    run_dir = os.path.join(run_root, cfg.tag())
    os.makedirs(run_dir, exist_ok=True)
    argv = build_argv(cfg, run_dir, gem5_bin, script)

    t0 = time.time()
    with open(os.path.join(run_dir, "stdout.txt"), "wb") as out, open(
        os.path.join(run_dir, "stderr.txt"), "wb"
    ) as err:
        try:
            proc = subprocess.run(
                argv, stdout=out, stderr=err, timeout=timeout
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc = -1
    wall = time.time() - t0

    meta = {
        "tag": cfg.tag(),
        "run_dir": run_dir,
        "cmd": argv,
        "returncode": rc,
        "wall_seconds": round(wall, 3),
        "git_hash": git_hash(),
        "stats_path": os.path.join(run_dir, "stats.txt"),
        "config": asdict(cfg),
    }
    with open(os.path.join(run_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return meta


if __name__ == "__main__":
    # Smoke test: one default run.
    root = os.path.join(REPO_ROOT, "experiments", "mcs_noc", "runs")
    os.makedirs(root, exist_ok=True)
    m = run(RunConfig(label="smoke", injectionrate=0.2), root)
    print(
        json.dumps(
            {k: m[k] for k in ("tag", "returncode", "wall_seconds")}, indent=2
        )
    )

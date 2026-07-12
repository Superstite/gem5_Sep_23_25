"""Real-workload NoC trace run for the motivation figures.

Runs 64 cores each executing a real MiBench benchmark (SE mode) on the 8x8
CustomMesh with MESI Two-Level Ruby, XY routing (baseline, no express). The
reconfiguration manager is enabled ONLY so GarnetNetwork::reconfigStep fires
each epoch and emits the per-router ReconTrace (RTRACE) stream; the watermark
is set so high that express links never actually activate -> a true baseline.

Unlike the synthetic LinearGenerator harness (100% memory-read traffic), this
produces realistic instruction+data+coherence traffic with real application
phases, so the motivation figures reflect a real-life workload.

Run:
  build/X86_MESI_Two_Level/gem5.debug --outdir=<od> --debug-flags=ReconTrace \
      configs/network/recon_bench_run.py --max-ticks 50000000
"""

import argparse

import m5

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_network import (
    MESITwoLevelCacheNetwork,
)
from gem5.components.memory import DualChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import CustomResource
from gem5.simulate.simulator import Simulator

NUM_CORES = 64  # fixed by the 8x8 CustomMesh
EPOCH_CYC = 100  # RTRACE sampling epoch (cycles)
# HC source cores -- SAME set used by the synthetic motivation figures so the
# criticality split is consistent across figures.
HC_SRCS = [0, 3, 10, 20, 29, 35, 48, 59]

p = argparse.ArgumentParser()
p.add_argument(
    "--max-ticks",
    type=int,
    default=50_000_000,
    help="Stop after this many ticks (1 cycle = 1000 ticks @1GHz).",
)
p.add_argument(
    "--routing-algo",
    type=int,
    default=1,
    help="1 = XY baseline (no express), matches Fig.2/Fig.3.",
)
p.add_argument(
    "--express-active",
    type=int,
    default=0,
    help="1 = express links active at init (static-all).",
)
p.add_argument(
    "--reconfig-policy",
    type=int,
    default=0,
    help="0 = per-router, 1 = global HC-onset (reactive).",
)
p.add_argument(
    "--hc-hi",
    type=int,
    default=999_999_999,
    help="Policy 1 reactive: global HC pkts/epoch onset threshold.",
)
p.add_argument(
    "--hc-lo",
    type=int,
    default=0,
    help="Policy 1 reactive: global HC pkts/epoch release threshold.",
)
p.add_argument(
    "--mc-merge",
    type=int,
    default=0,
    help="1 = enable elastic VC merging at MC routers (Phase 7c).",
)
p.add_argument(
    "--mc-hc-hi",
    type=int,
    default=80,
    help="F1: HC pkts/epoch at an MC router to arm VC merge.",
)
p.add_argument(
    "--mc-lc-lo",
    type=int,
    default=400,
    help="F2: LC pkts/epoch below which the donor VC is idle.",
)
args = p.parse_args()

# --- MiBench binaries (real workloads) -------------------------------------
MB = "/home/sneha/Github_Repos/mibench"
bins_args = [
    (
        f"{MB}/automotive/susan/susan",
        [
            f"{MB}/automotive/susan/input_large.pgm",
            f"{MB}/automotive/susan/output_large.smoothing.pgm",
            "-s",
        ],
    ),
    (
        f"{MB}/automotive/qsort/qsort_large",
        [f"{MB}/automotive/qsort/input_large.dat"],
    ),
    (f"{MB}/automotive/bitcount/bitcnts", ["bitcnts", "1125000"]),
    (f"{MB}/automotive/basicmath/basicmath_small", [""]),
    (f"{MB}/telecomm/CRC32/crc", [f"{MB}/telecomm/adpcm/data/large.pcm"]),
    (
        f"{MB}/network/dijkstra/dijkstra_large",
        [f"{MB}/network/dijkstra/input.dat"],
    ),
    (f"{MB}/network/patricia/patricia", [f"{MB}/network/patricia/large.udp"]),
]

# Build exactly NUM_CORES (binary, args) pairs by cycling the 7 benchmarks.
binaries, arguments = [], []
for i in range(NUM_CORES):
    path, a = bins_args[i % len(bins_args)]
    binaries.append(CustomResource(path))
    arguments.append(a)

cache_hierarchy = MESITwoLevelCacheNetwork(
    l1d_size="32kB",
    l1d_assoc=8,
    l1i_size="32kB",
    l1i_assoc=8,
    l2_size="256kB",
    l2_assoc=16,
    num_l2_banks=2,
    high_criticality_src_ids=HC_SRCS,
    routing_algorithm=args.routing_algo,  # 1 = XY baseline, 2 = express
    express_active=bool(args.express_active),  # static-all if 1
    # Enable reconfigStep so RTRACE fires; per-router watermark kept high so
    # Policy 0 never self-activates (baseline). Reactive uses Policy 1 below.
    reconfig_enable=True,
    reconfig_epoch=EPOCH_CYC,
    reconfig_high_wm=999_999_999,
    reconfig_low_wm=0,
    reconfig_policy=args.reconfig_policy,
    reconfig_hc_hi=args.hc_hi,
    reconfig_hc_lo=args.hc_lo,
    mc_merge_enable=bool(args.mc_merge),
    mc_hc_hi=args.mc_hc_hi,
    mc_lc_lo=args.mc_lc_lo,
)

memory = DualChannelDDR4_2400(size="8GB")
processor = SimpleProcessor(
    cpu_type=CPUTypes.TIMING,
    isa=ISA.X86,
    num_cores=NUM_CORES,
)
board = SimpleBoard(
    clk_freq="1GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# exit_on_work_items=False so an early benchmark exit does not stop the whole
# run; we bound the run with max_ticks instead to capture a trace window.
board.set_se_multi_binary_workload(
    binaries=binaries,
    arguments=arguments,
    exit_on_work_items=False,
)

simulator = Simulator(board=board)
simulator.run(max_ticks=args.max_ticks)
print(
    "Exiting @ tick {} because {}.".format(
        simulator.get_current_tick(), simulator.get_last_exit_event_cause()
    )
)

"""Reconfigurable-topology project: synthetic mixed-criticality traffic harness.

64 linear-generator cores on the 8x8 CustomMesh. HC cores (--high-crit-srcs)
stream at --hc-rate, the rest at --lc-rate. Used to exercise / evaluate runtime
skippable-link activation.

Verify criticality propagation into Garnet (Phase 1):
  gem5.debug --debug-flags=RubyNetwork recon_traffic.py --high-crit-srcs 0,1,2 \
      --duration 0.01ms 2>&1 | grep "RECONF" | grep "is_hc=1" | head
"""

import argparse

from gem5.components.boards.test_board import TestBoard
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_network import (
    MESITwoLevelCacheNetwork,
)
from gem5.components.memory import DualChannelDDR4_2400
from gem5.components.processors.abstract_generator import (
    AbstractGenerator,
    partition_range,
)
from gem5.components.processors.linear_generator_core import (
    LinearGeneratorCore,
)
from gem5.simulate.simulator import Simulator
from gem5.utils.override import overrides

NUM_CORES = 64  # fixed by the 8x8 CustomMesh


class MixedRateLinearGenerator(AbstractGenerator):
    def __init__(
        self,
        hc_srcs,
        hc_rate,
        lc_rate,
        duration,
        block_size,
        min_addr,
        max_addr,
        rd_perc,
    ):
        ranges = partition_range(min_addr, max_addr, NUM_CORES)
        cores = [
            LinearGeneratorCore(
                duration=duration,
                rate=(hc_rate if i in hc_srcs else lc_rate),
                block_size=block_size,
                min_addr=ranges[i][0],
                max_addr=ranges[i][1],
                rd_perc=rd_perc,
                data_limit=0,
            )
            for i in range(NUM_CORES)
        ]
        super().__init__(cores=cores)

    @overrides(AbstractGenerator)
    def start_traffic(self):
        for c in self.cores:
            c.start_traffic()


p = argparse.ArgumentParser()
p.add_argument("--duration", default="0.04ms")
p.add_argument("--hc-rate", default="0.5GiB/s")
p.add_argument("--lc-rate", default="1.0GiB/s")
p.add_argument("--max-addr", type=int, default=4 * 1024**3)
p.add_argument("--rd-perc", type=int, default=100)
p.add_argument("--max-ticks", type=int, default=0)
p.add_argument("--high-crit-srcs", default="")
p.add_argument(
    "--routing-algo",
    type=int,
    default=2,
    help="1 = XY baseline (no express), 2 = custom express routing.",
)
args = p.parse_args()

hc_srcs = [int(x) for x in args.high_crit_srcs.split(",") if x.strip() != ""]

cache_hierarchy = MESITwoLevelCacheNetwork(
    l1d_size="32kB",
    l1d_assoc=8,
    l1i_size="32kB",
    l1i_assoc=8,
    l2_size="256kB",
    l2_assoc=16,
    num_l2_banks=2,
    high_criticality_src_ids=hc_srcs,
    routing_algorithm=args.routing_algo,
)

generator = MixedRateLinearGenerator(
    hc_srcs=set(hc_srcs),
    hc_rate=args.hc_rate,
    lc_rate=args.lc_rate,
    duration=args.duration,
    block_size=64,
    min_addr=0,
    max_addr=args.max_addr,
    rd_perc=args.rd_perc,
)

board = TestBoard(
    clk_freq="1GHz",
    generator=generator,
    memory=DualChannelDDR4_2400(size="8GB"),
    cache_hierarchy=cache_hierarchy,
)

print(
    f"[recon] cores={NUM_CORES} n_hc={len(hc_srcs)} dur={args.duration} "
    f"hc_rate={args.hc_rate} lc_rate={args.lc_rate}"
)

simulator = Simulator(board=board)
if args.max_ticks > 0:
    simulator.run(max_ticks=args.max_ticks)
else:
    simulator.run()
print(
    "[recon] exit @ tick {} cause={}".format(
        simulator.get_current_tick(), simulator.get_last_exit_event_cause()
    )
)

"""Reconfigurable-topology project: synthetic mixed-criticality traffic harness.

64 linear-generator cores on the 8x8 CustomMesh. HC cores (--high-crit-srcs)
stream at --hc-rate, the rest at --lc-rate. Used to exercise / evaluate runtime
skippable-link activation.

Verify criticality propagation into Garnet (Phase 1):
  gem5.debug --debug-flags=RubyNetwork recon_traffic.py --high-crit-srcs 0,1,2 \
      --duration 0.01ms 2>&1 | grep "RECONF" | grep "is_hc=1" | head
"""

import argparse

from m5.ticks import fromSeconds
from m5.util.convert import (
    toLatency,
    toMemoryBandwidth,
)

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


class BurstyGeneratorCore(LinearGeneratorCore):
    """A LinearGeneratorCore that injects in ON/OFF bursts: it streams at the
    given rate for ``burst`` time, idles for ``gap`` time, and repeats for the
    whole ``duration``. This creates the temporal slack a runtime-elastic NoC
    can exploit -- and a multifractal/self-similar HC arrival series the
    predictive controller is calibrated against."""

    def __init__(self, burst: str, gap: str, warmup: str = "", **kw):
        super().__init__(**kw)
        self._burst = burst
        self._gap = gap
        self._warmup = warmup

    @overrides(LinearGeneratorCore)
    def _create_traffic(self):
        total = fromSeconds(toLatency(self._duration))
        burst = fromSeconds(toLatency(self._burst))
        gap = fromSeconds(toLatency(self._gap))
        rate = toMemoryBandwidth(self._rate)
        period = fromSeconds(self._block_size / rate)
        elapsed = 0
        # Optional HC warmup: stay idle while the LC background reaches steady
        # state and the predictor's EWMA settles, so the first HC burst does
        # not hit a cold/uninitialised network (avoids an initial collapse
        # that would dominate the average and mask per-burst behaviour).
        if self._warmup:
            w = min(fromSeconds(toLatency(self._warmup)), total)
            yield self.generator.createIdle(w)
            elapsed += w
        while elapsed < total:
            b = min(burst, total - elapsed)
            yield self.generator.createLinear(
                b,
                self._min_addr,
                self._max_addr,
                self._block_size,
                period,
                period,
                self._rd_perc,
                self._data_limit,
            )
            elapsed += b
            if elapsed >= total:
                break
            g = min(gap, total - elapsed)
            yield self.generator.createIdle(g)
            elapsed += g
        yield self.generator.createExit(0)


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
        hc_burst="",
        hc_gap="",
        hc_warmup="",
    ):
        ranges = partition_range(min_addr, max_addr, NUM_CORES)
        bursty = bool(hc_burst) and bool(hc_gap)

        def make_core(i):
            common = dict(
                duration=duration,
                rate=(hc_rate if i in hc_srcs else lc_rate),
                block_size=block_size,
                min_addr=ranges[i][0],
                max_addr=ranges[i][1],
                rd_perc=rd_perc,
                data_limit=0,
            )
            # HC cores burst (ON/OFF); LC cores stream steadily as a background.
            if bursty and i in hc_srcs:
                return BurstyGeneratorCore(
                    burst=hc_burst, gap=hc_gap, warmup=hc_warmup, **common
                )
            return LinearGeneratorCore(**common)

        cores = [make_core(i) for i in range(NUM_CORES)]
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
p.add_argument(
    "--express-active",
    type=int,
    default=0,
    help="1 = express links active at start, 0 = inactive (baseline).",
)
p.add_argument(
    "--reconfig",
    type=int,
    default=0,
    help="1 = enable runtime reconfiguration manager (Phase 4).",
)
p.add_argument(
    "--epoch",
    type=int,
    default=5000,
    help="Reconfiguration decision interval in cycles.",
)
p.add_argument(
    "--high-wm",
    type=int,
    default=400,
    help="Flits/epoch/router to activate express links.",
)
p.add_argument(
    "--low-wm",
    type=int,
    default=150,
    help="Flits/epoch/router to deactivate express links.",
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
    help="F1: HC flits/epoch at MC router to arm VC merge.",
)
p.add_argument(
    "--mc-lc-lo",
    type=int,
    default=400,
    help="F2: LC flits/epoch below which the donor VC is idle.",
)
p.add_argument(
    "--reconfig-policy",
    type=int,
    default=0,
    help="0 = per-router, 1 = global HC-onset, 2 = predictive (EWMA+slope).",
)
p.add_argument(
    "--hc-hi",
    type=int,
    default=200,
    help="Policy 1/2: network-wide HC flits/epoch onset threshold.",
)
p.add_argument(
    "--hc-lo",
    type=int,
    default=60,
    help="Policy 1/2: network-wide HC flits/epoch release threshold.",
)
p.add_argument(
    "--ewma-alpha",
    type=float,
    default=0.5,
    help="Policy 2: EWMA smoothing for global HC demand.",
)
p.add_argument(
    "--slope-hi",
    type=int,
    default=40,
    help="Policy 2: leading-edge (demand-EWMA) arm trigger.",
)
p.add_argument(
    "--hold-epochs",
    type=int,
    default=8,
    help="Policy 2: epochs to hold express on (MFDFA-sized).",
)
p.add_argument(
    "--rl-train",
    type=int,
    default=0,
    help="Policy 3: 1 = learn + write Q-table, 0 = load + freeze.",
)
p.add_argument(
    "--q-file",
    default="",
    help="Policy 3: Q-table path (write when training, read when "
    "deploying).",
)
p.add_argument("--rl-lr", type=float, default=0.2)
p.add_argument("--rl-eps", type=float, default=0.2)
p.add_argument("--rl-gamma", type=float, default=0.9)
p.add_argument(
    "--rl-lambda",
    type=float,
    default=0.5,
    help="Policy 3: reward weight on express-on (duty penalty).",
)
p.add_argument("--rl-occ-scale", type=float, default=100.0)
p.add_argument("--rl-seed", type=int, default=1)
p.add_argument(
    "--sched-start",
    type=int,
    default=0,
    help="Policy 4 oracle: ticks before first burst window.",
)
p.add_argument(
    "--sched-period",
    type=int,
    default=1,
    help="Policy 4 oracle: burst period in ticks.",
)
p.add_argument(
    "--sched-on",
    type=int,
    default=0,
    help="Policy 4 oracle: express-ON width per period in ticks.",
)
p.add_argument(
    "--sched-lead",
    type=int,
    default=0,
    help="Policy 4 oracle: pre-arm ticks before each burst.",
)
p.add_argument(
    "--hc-burst",
    default="",
    help="Bursty HC: ON duration per burst, e.g. 2000ns. Empty=off.",
)
p.add_argument(
    "--hc-gap",
    default="",
    help="Bursty HC: OFF (idle) duration between bursts, e.g. 3000ns.",
)
p.add_argument(
    "--hc-warmup",
    default="",
    help="Bursty HC: initial idle before bursts start (LC-only "
    "warmup so the first burst hits a steady network).",
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
    express_active=bool(args.express_active),
    reconfig_enable=bool(args.reconfig),
    reconfig_epoch=args.epoch,
    reconfig_high_wm=args.high_wm,
    reconfig_low_wm=args.low_wm,
    reconfig_policy=args.reconfig_policy,
    reconfig_hc_hi=args.hc_hi,
    reconfig_hc_lo=args.hc_lo,
    reconfig_ewma_alpha=args.ewma_alpha,
    reconfig_slope_hi=args.slope_hi,
    reconfig_hold_epochs=args.hold_epochs,
    reconfig_rl_train=bool(args.rl_train),
    reconfig_q_file=args.q_file,
    reconfig_rl_lr=args.rl_lr,
    reconfig_rl_eps=args.rl_eps,
    reconfig_rl_gamma=args.rl_gamma,
    reconfig_rl_lambda=args.rl_lambda,
    reconfig_rl_occ_scale=args.rl_occ_scale,
    reconfig_rl_seed=args.rl_seed,
    reconfig_sched_start=args.sched_start,
    reconfig_sched_period=args.sched_period,
    reconfig_sched_on=args.sched_on,
    reconfig_sched_lead=args.sched_lead,
    mc_merge_enable=bool(args.mc_merge),
    mc_hc_hi=args.mc_hc_hi,
    mc_lc_lo=args.mc_lc_lo,
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
    hc_burst=args.hc_burst,
    hc_gap=args.hc_gap,
    hc_warmup=args.hc_warmup,
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

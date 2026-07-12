# Copyright (c) 2008 Princeton University
# Copyright (c) 2009 Advanced Micro Devices, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Author: Tushar Krishna
#

from m5.citations import add_citation
from m5.objects.BasicRouter import BasicRouter
from m5.objects.ClockedObject import ClockedObject
from m5.objects.Network import RubyNetwork
from m5.params import *
from m5.proxy import *


class GarnetNetwork(RubyNetwork):
    type = "GarnetNetwork"
    cxx_header = "mem/ruby/network/garnet/GarnetNetwork.hh"
    cxx_class = "gem5::ruby::garnet::GarnetNetwork"

    num_rows = Param.Int(0, "number of rows if 2D (mesh/torus/..) topology")
    ni_flit_size = Param.UInt32(16, "network interface flit size in bytes")
    vcs_per_vnet = Param.UInt32(4, "virtual channels per virtual network")
    buffers_per_data_vc = Param.UInt32(4, "buffers per data virtual channel")
    buffers_per_ctrl_vc = Param.UInt32(1, "buffers per ctrl virtual channel")
    routing_algorithm = Param.Int(0, "0: Weight-based Table, 1: XY, 2: Custom")
    express_active = Param.Bool(
        False,
        "Phase 3: initial activation state of 2-hop express links (custom "
        "routing). False = baseline; manager may toggle per-router at runtime.",
    )
    reconfig_enable = Param.Bool(
        False,
        "Phase 4: enable the runtime express-link reconfiguration manager.",
    )
    reconfig_epoch = Param.Cycles(
        5000, "Cycles between reconfiguration decisions."
    )
    reconfig_high_wm = Param.UInt64(
        400, "Per-router flits/epoch above which express links activate."
    )
    reconfig_low_wm = Param.UInt64(
        150, "Per-router flits/epoch below which express links deactivate."
    )
    reconfig_policy = Param.Int(
        0,
        "Express-activation policy. 0 = per-router flit-threshold (legacy, "
        "reactive -- fires AFTER congestion collapse). 1 = global HC-onset: "
        "activate express broadly when network-wide HC demand crosses "
        "reconfig_hc_hi, release below reconfig_hc_lo (fine epoch, broad, "
        "still reactive). 2 = predictive: EWMA + leading-edge slope trigger "
        "with a persistence-derived hold, so express arms on the burst's "
        "rising edge BEFORE collapse and holds through the (multifractally "
        "persistent) burst, then releases in the gap (elastic). The EWMA/"
        "hold/threshold constants are calibrated OFFLINE by MFDFA on the HC "
        "trace; no multifractal math runs at simulation time.",
    )
    reconfig_hc_hi = Param.UInt64(
        200, "Policy 1/2: network-wide HC flits/epoch onset threshold."
    )
    reconfig_hc_lo = Param.UInt64(
        60, "Policy 1/2: network-wide HC flits/epoch release threshold."
    )
    reconfig_ewma_alpha = Param.Float(
        0.5, "Policy 2: EWMA smoothing factor for global HC demand (0..1)."
    )
    reconfig_slope_hi = Param.Int(
        40,
        "Policy 2: leading-edge trigger -- arm express when (demand - EWMA) "
        "rises past this (burst onset predicted before the threshold is even "
        "reached).",
    )
    reconfig_hold_epochs = Param.UInt64(
        8,
        "Policy 2: epochs to hold express active after arming (hysteresis), "
        "sized from the offline MFDFA persistence estimate h(2).",
    )
    # Policy 3: tabular Q-learning express controller. State = [HC-demand bin x
    # slope sign x recency-since-last-burst x express-state]; action = express
    # all-on/all-off; reward = -(network buffer occupancy + rl_lambda*on). A
    # recency feature lets it ANTICIPATE periodic bursts (unlike EWMA/slope).
    # Train once (eps-greedy, TD updates) -> dump Q; deploy frozen (greedy).
    reconfig_rl_train = Param.Bool(
        False,
        "Policy 3: True = learn + write Q to reconfig_q_file; "
        "False = load Q and act greedily (frozen).",
    )
    reconfig_q_file = Param.String(
        "",
        "Policy 3: path to the Q-table (written when training, read when "
        "deploying).",
    )
    reconfig_rl_lr = Param.Float(0.2, "Policy 3: Q-learning rate.")
    reconfig_rl_eps = Param.Float(0.2, "Policy 3: eps-greedy exploration.")
    reconfig_rl_gamma = Param.Float(0.9, "Policy 3: discount factor.")
    reconfig_rl_lambda = Param.Float(
        0.5, "Policy 3: reward weight on express-on cost (duty penalty)."
    )
    reconfig_rl_occ_scale = Param.Float(
        100.0,
        "Policy 3: divisor normalising the occupancy term of the reward.",
    )
    reconfig_rl_seed = Param.Int(1, "Policy 3: RNG seed for eps-greedy.")
    # Policy 4: ORACLE periodic schedule -- express ON during known burst
    # windows (+ optional lead). Measures the best achievable HC-vs-duty point
    # given perfect burst foreknowledge -> tells us if any predictor has room
    # to beat the reactive controller.
    reconfig_sched_start = Param.UInt64(
        0, "Policy 4: ticks before the first burst window (warmup)."
    )
    reconfig_sched_period = Param.UInt64(
        1, "Policy 4: burst period in ticks (burst+gap)."
    )
    reconfig_sched_on = Param.UInt64(
        0, "Policy 4: express-ON width per period in ticks (burst length)."
    )
    reconfig_sched_lead = Param.UInt64(
        0, "Policy 4: ticks to pre-arm express before each burst window."
    )
    mc_router_ids = VectorParam.Int(
        [],
        "Phase 7: router ids hosting a memory-controller (Directory) endpoint "
        "-- where HC funnels and the sink VC bottleneck forms.",
    )
    mc_merge_enable = Param.Bool(
        False,
        "Phase 7c: enable elastic VC merging at MC routers (HC borrows the "
        "idle donor VC under a two-factor burst-and-slack gate).",
    )
    mc_hc_hi = Param.UInt64(
        80, "Phase 7c F1: HC flits/epoch at an MC router to arm VC merge."
    )
    mc_lc_lo = Param.UInt64(
        400, "Phase 7c F2: LC flits/epoch below which the donor VC is idle."
    )
    enable_fault_model = Param.Bool(False, "enable network fault model")
    fault_model = Param.FaultModel(NULL, "network fault model")
    garnet_deadlock_threshold = Param.UInt32(
        50000, "network-level deadlock threshold"
    )
    num_rows = Param.Int(4, "Number of rows")
    num_cols = Param.Int(4, "Number of columns")


class GarnetNetworkInterface(ClockedObject):
    type = "GarnetNetworkInterface"
    cxx_class = "gem5::ruby::garnet::NetworkInterface"
    cxx_header = "mem/ruby/network/garnet/NetworkInterface.hh"

    id = Param.UInt32("ID in relation to other network interfaces")
    vcs_per_vnet = Param.UInt32(
        Parent.vcs_per_vnet, "virtual channels per virtual network"
    )
    virt_nets = Param.UInt32(
        Parent.number_of_virtual_networks, "number of virtual networks"
    )
    garnet_deadlock_threshold = Param.UInt32(
        Parent.garnet_deadlock_threshold, "network-level deadlock threshold"
    )


class GarnetRouter(BasicRouter):
    type = "GarnetRouter"
    cxx_class = "gem5::ruby::garnet::Router"
    cxx_header = "mem/ruby/network/garnet/Router.hh"
    vcs_per_vnet = Param.UInt32(
        Parent.vcs_per_vnet, "virtual channels per virtual network"
    )
    virt_nets = Param.UInt32(
        Parent.number_of_virtual_networks, "number of virtual networks"
    )
    width = Param.UInt32(
        Parent.ni_flit_size, "bit width supported by the router"
    )


add_citation(
    GarnetNetwork,
    """@inproceedings{Bharadwaj:2020:kite,
  author       = {Srikant Bharadwaj and
                  Jieming Yin and
                  Bradford M. Beckmann and
                  Tushar Krishna},
  title        = {Kite: {A} Family of Heterogeneous Interposer Topologies Enabled via
                  Accurate Interconnect Modeling},
  booktitle    = {57th {ACM/IEEE} Design Automation Conference, {DAC} 2020, San Francisco,
                  CA, USA, July 20-24, 2020},
  pages        = {1--6},
  publisher    = {{IEEE}},
  year         = {2020},
  url          = {https://doi.org/10.1109/DAC18072.2020.9218539},
  doi          = {10.1109/DAC18072.2020.9218539}
}
@inproceedings{Agarwal:2009:garnet,
  author       = {Niket Agarwal and
                  Tushar Krishna and
                  Li{-}Shiuan Peh and
                  Niraj K. Jha},
  title        = {{GARNET:} {A} detailed on-chip network model inside a full-system
                  simulator},
  booktitle    = {{IEEE} International Symposium on Performance Analysis of Systems
                  and Software, {ISPASS} 2009, April 26-28, 2009, Boston, Massachusetts,
                  USA, Proceedings},
  pages        = {33--42},
  publisher    = {{IEEE} Computer Society},
  year         = {2009},
  url          = {https://doi.org/10.1109/ISPASS.2009.4919636},
  doi          = {10.1109/ISPASS.2009.4919636}
}
""",
)

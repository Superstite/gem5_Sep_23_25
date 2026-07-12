/*
 * Copyright (c) 2020 Advanced Micro Devices, Inc.
 * Copyright (c) 2008 Princeton University
 * Copyright (c) 2016 Georgia Institute of Technology
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met: redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer;
 * redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution;
 * neither the name of the copyright holders nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */


#include "mem/ruby/network/garnet/GarnetNetwork.hh"

#include <algorithm>
#include <cassert>

#include "base/cast.hh"
#include "base/compiler.hh"
#include "debug/ReconTrace.hh"
#include "debug/RubyNetwork.hh"
#include "mem/ruby/common/NetDest.hh"
#include "mem/ruby/network/MessageBuffer.hh"
#include "mem/ruby/network/garnet/CommonTypes.hh"
#include "mem/ruby/network/garnet/CreditLink.hh"
#include "mem/ruby/network/garnet/GarnetLink.hh"
#include "mem/ruby/network/garnet/NetworkInterface.hh"
#include "mem/ruby/network/garnet/NetworkLink.hh"
#include "mem/ruby/network/garnet/Router.hh"
#include "mem/ruby/system/RubySystem.hh"

namespace gem5
{

namespace ruby
{

namespace garnet
{

/*
 * GarnetNetwork sets up the routers and links and collects stats.
 * Default parameters (GarnetNetwork.py) can be overwritten from command line
 * (see configs/network/Network.py)
 */

GarnetNetwork::GarnetNetwork(const Params &p)
    : Network(p),
      m_reconfig_event([this]{ reconfigStep(); }, name() + ".reconfig"),
      m_reconfig_enable(p.reconfig_enable),
      m_reconfig_epoch(p.reconfig_epoch),
      m_reconfig_high_wm(p.reconfig_high_wm),
      m_reconfig_low_wm(p.reconfig_low_wm),
      m_reconfig_policy(p.reconfig_policy),
      m_reconfig_hc_hi(p.reconfig_hc_hi),
      m_reconfig_hc_lo(p.reconfig_hc_lo),
      m_reconfig_ewma_alpha(p.reconfig_ewma_alpha),
      m_reconfig_slope_hi(p.reconfig_slope_hi),
      m_reconfig_hold_epochs(p.reconfig_hold_epochs),
      m_rl_train(p.reconfig_rl_train),
      m_q_file(p.reconfig_q_file),
      m_rl_lr(p.reconfig_rl_lr),
      m_rl_eps(p.reconfig_rl_eps),
      m_rl_gamma(p.reconfig_rl_gamma),
      m_rl_lambda(p.reconfig_rl_lambda),
      m_rl_occ_scale(p.reconfig_rl_occ_scale),
      m_rl_seed(p.reconfig_rl_seed),
      m_sched_start(p.reconfig_sched_start),
      m_sched_period(p.reconfig_sched_period),
      m_sched_on(p.reconfig_sched_on),
      m_sched_lead(p.reconfig_sched_lead),
      m_mc_merge_enable(p.mc_merge_enable),
      m_mc_hc_hi(p.mc_hc_hi),
      m_mc_lc_lo(p.mc_lc_lo)
{
    m_num_rows = p.num_rows;
    m_ni_flit_size = p.ni_flit_size;
    m_max_vcs_per_vnet = 0;
    m_buffers_per_data_vc = p.buffers_per_data_vc;
    m_buffers_per_ctrl_vc = p.buffers_per_ctrl_vc;
    m_routing_algorithm = p.routing_algorithm;
    m_next_packet_id = 0;

    m_enable_fault_model = p.enable_fault_model;
    if (m_enable_fault_model)
        fault_model = p.fault_model;

    m_vnet_type.resize(m_virtual_networks);
    m_num_rows = p.num_rows;
    m_num_cols = p.num_cols;

    for (int i = 0 ; i < m_virtual_networks ; i++) {
        if (m_vnet_type_names[i] == "response")
            m_vnet_type[i] = DATA_VNET_; // carries data (and ctrl) packets
        else
            m_vnet_type[i] = CTRL_VNET_; // carries only ctrl packets
    }

    // record the routers
    for (std::vector<BasicRouter*>::const_iterator i =  p.routers.begin();
         i != p.routers.end(); ++i) {
        Router* router = safe_cast<Router*>(*i);
        m_routers.push_back(router);

        // initialize the router's network pointers
        router->init_net_ptr(this);

        // Phase 3: seed the express-link activation state from the param.
        router->setExpressActive(p.express_active);
    }

    // Phase 7a: tag memory-controller (sink) routers.
    for (int id : p.mc_router_ids) {
        assert(id >= 0 && id < (int)m_routers.size());
        m_routers[id]->setMcRouter(true);
    }

    // record the network interfaces
    for (std::vector<ClockedObject*>::const_iterator i = p.netifs.begin();
         i != p.netifs.end(); ++i) {
        NetworkInterface *ni = safe_cast<NetworkInterface *>(*i);
        m_nis.push_back(ni);
        ni->init_net_ptr(this);
    }

    // Print Garnet version
    inform("Garnet version %s\n", garnetVersion);
}

void
GarnetNetwork::setRouterExpressActive(int router_id, bool active)
{
    assert(router_id >= 0 && router_id < (int)m_routers.size());
    m_routers[router_id]->setExpressActive(active);
}

void
GarnetNetwork::setAllExpressActive(bool active)
{
    for (auto *router : m_routers) {
        router->setExpressActive(active);
    }
}

void
GarnetNetwork::setMcVcMerge(int router_id, bool active)
{
    assert(router_id >= 0 && router_id < (int)m_routers.size());
    m_routers[router_id]->setVcMerge(active);
}

void
GarnetNetwork::startup()
{
    // Policy 3 (RL): seed the RNG and load the Q-table (trained if deploying,
    // zero-initialised if training from scratch).
    if (m_reconfig_enable && m_reconfig_policy == 3) {
        m_rl_rng.seed((uint32_t)m_rl_seed);
        rlLoadQ();
    }
    // Kick off the periodic reconfiguration manager once simulation starts.
    // Runs if either actuator is enabled: express-link reconfig (Phase 4) or
    // MC-router VC merging (Phase 7c).
    if (m_reconfig_enable || m_mc_merge_enable) {
        schedule(m_reconfig_event, clockEdge(m_reconfig_epoch));
    }
}

void
GarnetNetwork::reconfigStep()
{
    // Sample every router this epoch, then actuate express per the chosen
    // policy. Per-router HC/LC counts are summed network-wide to drive the
    // global (policy 1) and predictive (policy 2) express activation.
    uint64_t global_hc = 0;
    for (int i = 0; i < (int)m_routers.size(); i++) {
        uint64_t packets = m_routers[i]->consumeEpochPacketCount();
        uint64_t hc = m_routers[i]->consumeEpochHcPacketCount();
        uint64_t lc = m_routers[i]->consumeEpochLcPacketCount();
        global_hc += hc;

        bool is_mc = m_routers[i]->isMcRouter();
        uint64_t mc_hcocc = 0, mc_dnocc = 0;

        // Policy 0 (legacy): per-router packet-threshold actuator with
        // hysteresis. Reactive -- fires only after a router is already
        // congested, i.e. after the mesh has begun to collapse. Kept for
        // comparison.
        if (m_reconfig_enable && m_reconfig_policy == 0) {
            bool active = m_routers[i]->getExpressActive();
            if (!active && packets >= m_reconfig_high_wm) {
                m_routers[i]->setExpressActive(true);
                DPRINTF(RubyNetwork, "RECONF_MGR R%d ACTIVATE packets=%llu\n",
                        i, (unsigned long long)packets);
            } else if (active && packets <= m_reconfig_low_wm) {
                m_routers[i]->setExpressActive(false);
                DPRINTF(RubyNetwork,
                        "RECONF_MGR R%d DEACTIVATE packets=%llu\n",
                        i, (unsigned long long)packets);
            }
        }

        // Phase 7a/c: two-factor VC-merge sensing/gate at MC (directory/hub)
        // routers.
        if (is_mc) {
            m_routers[i]->getCritVcOccupancy(mc_hcocc, mc_dnocc);
            DPRINTF(RubyNetwork, "RECONF_MC R%d hc=%llu lc=%llu\n",
                    i, (unsigned long long)hc, (unsigned long long)lc);
            if (m_mc_merge_enable) {
                bool armed = m_routers[i]->getVcMerge();
                if (!armed && hc >= m_mc_hc_hi && lc <= m_mc_lc_lo) {
                    m_routers[i]->setVcMerge(true);
                    DPRINTF(RubyNetwork,
                            "RECONF_MERGE R%d ARM hc=%llu lc=%llu\n",
                            i, (unsigned long long)hc, (unsigned long long)lc);
                } else if (armed && (hc < m_mc_hc_hi || lc > m_mc_lc_lo)) {
                    m_routers[i]->setVcMerge(false);
                    DPRINTF(RubyNetwork,
                            "RECONF_MERGE R%d DISARM hc=%llu lc=%llu\n",
                            i, (unsigned long long)hc, (unsigned long long)lc);
                }
            }
        }

        // Per-router congestion + express-state trace (real eval data).
        // 'packets' = packets routed this epoch (all vnets); hc/lc = same,
        // split by criticality; hcocc/dnocc = genuine per-VC flit occupancy.
        DPRINTF(ReconTrace,
                "RTRACE t=%llu R%d packets=%llu mc=%d hc=%llu lc=%llu "
                "hcocc=%llu dnocc=%llu ex=%d\n",
                (unsigned long long)curTick(), i,
                (unsigned long long)packets, is_mc ? 1 : 0,
                (unsigned long long)hc, (unsigned long long)lc,
                (unsigned long long)mc_hcocc, (unsigned long long)mc_dnocc,
                m_routers[i]->getExpressActive() ? 1 : 0);
    }

    // Global express policies (decided once from network-wide HC demand).
    if (m_reconfig_enable && m_reconfig_policy == 1) {
        // Reactive-global: broad on/off by HC-demand watermarks. Broad + fine
        // epoch beats per-router, but still crosses the threshold only after
        // demand (and queueing) is already high.
        if (!m_express_all_on && global_hc >= m_reconfig_hc_hi) {
            setAllExpressActive(true); m_express_all_on = true;
            DPRINTF(RubyNetwork, "RECONF_GLOBAL ON hc=%llu\n",
                    (unsigned long long)global_hc);
        } else if (m_express_all_on && global_hc <= m_reconfig_hc_lo) {
            setAllExpressActive(false); m_express_all_on = false;
            DPRINTF(RubyNetwork, "RECONF_GLOBAL OFF hc=%llu\n",
                    (unsigned long long)global_hc);
        }
    } else if (m_reconfig_enable && m_reconfig_policy == 2) {
        // Predictive: EWMA + leading-edge slope arm express on the burst's
        // RISING edge (before the absolute threshold, before collapse); hold
        // for m_reconfig_hold_epochs (sized offline from the HC trace's MFDFA
        // persistence h(2)) so express stays on through the persistent burst,
        // then releases in the gap. All O(1) -- no multifractal math here.
        m_hc_ewma = (1.0 - m_reconfig_ewma_alpha) * m_hc_ewma +
                    m_reconfig_ewma_alpha * (double)global_hc;
        double slope = (double)global_hc - m_hc_ewma;
        bool onset = (global_hc >= m_reconfig_hc_hi) ||
                     (slope >= (double)m_reconfig_slope_hi);
        if (onset) {
            if (!m_express_all_on) {
                setAllExpressActive(true); m_express_all_on = true;
                DPRINTF(RubyNetwork,
                        "RECONF_PRED ARM hc=%llu ewma=%.1f slope=%.1f\n",
                        (unsigned long long)global_hc, m_hc_ewma, slope);
            }
            m_hold_left = m_reconfig_hold_epochs;   // (re)arm hold
        } else if (m_hold_left > 0) {
            m_hold_left--;                          // hold through the burst
        } else if (m_express_all_on && global_hc <= m_reconfig_hc_lo) {
            setAllExpressActive(false); m_express_all_on = false;
            DPRINTF(RubyNetwork, "RECONF_PRED RELEASE hc=%llu\n",
                    (unsigned long long)global_hc);
        }
    } else if (m_reconfig_enable && m_reconfig_policy == 3) {
        rlStep(global_hc);
    } else if (m_reconfig_enable && m_reconfig_policy == 4) {
        // Oracle: express ON during the known periodic burst window (+lead).
        // Upper bound on achievable HC-vs-duty with perfect foreknowledge.
        bool on = false;
        if (m_sched_period > 0 && curTick() >= m_sched_start) {
            uint64_t phase = (curTick() - m_sched_start) % m_sched_period;
            uint64_t lead_phase =
                (phase + m_sched_lead) % m_sched_period;   // pre-arm shift
            on = (phase < m_sched_on) || (lead_phase < m_sched_on);
        }
        if (on != m_express_all_on) {
            setAllExpressActive(on);
            m_express_all_on = on;
        }
    }

    schedule(m_reconfig_event, clockEdge(m_reconfig_epoch));
}

// ---- Policy 3: tabular Q-learning express controller ---------------------
namespace {
// State = demand(3) x slope(2) x recency(3) x express(2) = 36 states, 2 acts.
constexpr int RL_NSTATES = 36;
constexpr int RL_NACT = 2;
}

int
GarnetNetwork::rlState(uint64_t global_hc)
{
    // demand bin (via the same hc_lo/hc_hi thresholds as policies 1/2)
    int d = (global_hc <= m_reconfig_hc_lo) ? 0
          : (global_hc >= m_reconfig_hc_hi) ? 2 : 1;
    int s = ((double)global_hc > m_hc_ewma) ? 1 : 0;    // rising?
    // recency: epochs since the last demand burst -> lets the policy learn a
    // periodic burst cadence and pre-arm (anticipation slope trigger lacks)
    int rec = (m_rl_since_burst <= 2) ? 0
            : (m_rl_since_burst <= 15) ? 1 : 2;
    int e = m_express_all_on ? 1 : 0;
    return ((d * 2 + s) * 3 + rec) * 2 + e;
}

void
GarnetNetwork::rlStep(uint64_t global_hc)
{
    // Update the slow EWMA + burst-recency features.
    m_hc_ewma = (1.0 - m_reconfig_ewma_alpha) * m_hc_ewma +
                m_reconfig_ewma_alpha * (double)global_hc;
    if (global_hc >= m_reconfig_hc_hi)
        m_rl_since_burst = 0;
    else if (m_rl_since_burst < 1000000)
        m_rl_since_burst++;

    // Reward for the PREVIOUS (s,a): low HC congestion + low express cost.
    // Congestion term is HC-SPECIFIC (flits in HC-headed VCs) -- express
    // relieves HC but barely moves total (LC-dominated) occupancy, so a total-
    // occupancy reward makes express look like pure cost -> RL turns it off.
    uint64_t occ = 0;
    for (auto *r : m_routers)
        occ += r->getHcQueuedFlits();
    double reward = -((double)occ / m_rl_occ_scale +
                      m_rl_lambda * (m_express_all_on ? 1.0 : 0.0));

    int s_now = rlState(global_hc);
    // TD update Q[prev_s, prev_a] toward reward + gamma*max_a Q[s_now,a].
    if (m_rl_train && m_rl_prev_state >= 0) {
        double best_next = std::max(m_qtable[s_now * RL_NACT + 0],
                                    m_qtable[s_now * RL_NACT + 1]);
        double &q = m_qtable[m_rl_prev_state * RL_NACT + m_rl_prev_action];
        q += m_rl_lr * (reward + m_rl_gamma * best_next - q);
    }

    // Choose action for s_now: eps-greedy while training, greedy when frozen.
    int action;
    double q0 = m_qtable[s_now * RL_NACT + 0];
    double q1 = m_qtable[s_now * RL_NACT + 1];
    std::uniform_real_distribution<double> uni(0.0, 1.0);
    if (m_rl_train && uni(m_rl_rng) < m_rl_eps)
        action = (uni(m_rl_rng) < 0.5) ? 1 : 0;
    else
        action = (q1 > q0) ? 1 : 0;

    // Actuate express broadly per the chosen action.
    bool want_on = (action == 1);
    if (want_on != m_express_all_on) {
        setAllExpressActive(want_on);
        m_express_all_on = want_on;
    }
    DPRINTF(RubyNetwork, "RECONF_RL s=%d a=%d r=%.2f occ=%llu%s\n",
            s_now, action, reward, (unsigned long long)occ,
            m_rl_train ? " train" : " frozen");

    m_rl_prev_state = s_now;
    m_rl_prev_action = action;
    if (m_rl_train && !m_q_file.empty())
        rlSaveQ();   // persist online (72 doubles -- cheap)
}

void
GarnetNetwork::rlLoadQ()
{
    m_qtable.assign(RL_NSTATES * RL_NACT, 0.0);
    if (m_q_file.empty())
        return;
    std::ifstream in(m_q_file);
    if (!in.good())
        return;
    for (int i = 0; i < RL_NSTATES * RL_NACT && in >> m_qtable[i]; i++) {}
}

void
GarnetNetwork::rlSaveQ()
{
    std::ofstream out(m_q_file);
    for (int i = 0; i < RL_NSTATES * RL_NACT; i++)
        out << m_qtable[i] << (((i + 1) % RL_NACT == 0) ? '\n' : ' ');
}

void
GarnetNetwork::init()
{
    Network::init();

    for (int i=0; i < m_nodes; i++) {
        m_nis[i]->addNode(m_toNetQueues[i], m_fromNetQueues[i]);
    }

    // The topology pointer should have already been initialized in the
    // parent network constructor
    assert(m_topology_ptr != NULL);
    m_topology_ptr->createLinks(this);

    // Initialize topology specific parameters
    if (getNumRows() > 0) {
        // Only for Mesh topology
        // m_num_rows and m_num_cols are only used for
        // implementing XY or custom routing in RoutingUnit.cc
        m_num_rows = getNumRows();
        m_num_cols = m_routers.size() / m_num_rows;
        assert(m_num_rows * m_num_cols == m_routers.size());
    } else {
        m_num_rows = -1;
        m_num_cols = -1;
    }

    // FaultModel: declare each router to the fault model
    if (isFaultModelEnabled()) {
        for (std::vector<Router*>::const_iterator i= m_routers.begin();
             i != m_routers.end(); ++i) {
            Router* router = safe_cast<Router*>(*i);
            [[maybe_unused]] int router_id =
                fault_model->declare_router(router->get_num_inports(),
                                            router->get_num_outports(),
                                            router->get_vc_per_vnet(),
                                            getBuffersPerDataVC(),
                                            getBuffersPerCtrlVC());
            assert(router_id == router->get_id());
            router->printAggregateFaultProbability(std::cout);
            router->printFaultVector(std::cout);
        }
    }
}

/*
 * This function creates a link from the Network Interface (NI)
 * into the Network.
 * It creates a Network Link from the NI to a Router and a Credit Link from
 * the Router to the NI
*/

void
GarnetNetwork::makeExtInLink(NodeID global_src, SwitchID dest, BasicLink* link,
                             std::vector<NetDest>& routing_table_entry)
{
    NodeID local_src = getLocalNodeID(global_src);
    assert(local_src < m_nodes);

    GarnetExtLink* garnet_link = safe_cast<GarnetExtLink*>(link);

    // GarnetExtLink is bi-directional
    NetworkLink* net_link = garnet_link->m_network_links[LinkDirection_In];
    net_link->setType(EXT_IN_);
    CreditLink* credit_link = garnet_link->m_credit_links[LinkDirection_In];

    m_networklinks.push_back(net_link);
    m_creditlinks.push_back(credit_link);

    PortDirection dst_inport_dirn = "Local";

    m_max_vcs_per_vnet = std::max(m_max_vcs_per_vnet,
                             m_routers[dest]->get_vc_per_vnet());

    /*
     * We check if a bridge was enabled at any end of the link.
     * The bridge is enabled if either of clock domain
     * crossing (CDC) or Serializer-Deserializer(SerDes) unit is
     * enabled for the link at each end. The bridge encapsulates
     * the functionality for both CDC and SerDes and is a Consumer
     * object similiar to a NetworkLink.
     *
     * If a bridge was enabled we connect the NI and Routers to
     * bridge before connecting the link. Example, if an external
     * bridge is enabled, we would connect:
     * NI--->NetworkBridge--->GarnetExtLink---->Router
     */
    if (garnet_link->extBridgeEn) {
        DPRINTF(RubyNetwork, "Enable external bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->extNetBridge[LinkDirection_In];
        m_nis[local_src]->
        addOutPort(n_bridge,
                   garnet_link->extCredBridge[LinkDirection_In],
                   dest, m_routers[dest]->get_vc_per_vnet());
        m_networkbridges.push_back(n_bridge);
    } else {
        m_nis[local_src]->addOutPort(net_link, credit_link, dest,
            m_routers[dest]->get_vc_per_vnet());
    }

    if (garnet_link->intBridgeEn) {
        DPRINTF(RubyNetwork, "Enable internal bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->intNetBridge[LinkDirection_In];
        m_routers[dest]->
            addInPort(dst_inport_dirn,
                      n_bridge,
                      garnet_link->intCredBridge[LinkDirection_In]);
        m_networkbridges.push_back(n_bridge);
    } else {
        m_routers[dest]->addInPort(dst_inport_dirn, net_link, credit_link);
    }

}

/*
 * This function creates a link from the Network to a NI.
 * It creates a Network Link from a Router to the NI and
 * a Credit Link from NI to the Router
*/

void
GarnetNetwork::makeExtOutLink(SwitchID src, NodeID global_dest,
                              BasicLink* link,
                              std::vector<NetDest>& routing_table_entry)
{
    NodeID local_dest = getLocalNodeID(global_dest);
    assert(local_dest < m_nodes);
    assert(src < m_routers.size());
    assert(m_routers[src] != NULL);

    GarnetExtLink* garnet_link = safe_cast<GarnetExtLink*>(link);

    // GarnetExtLink is bi-directional
    NetworkLink* net_link = garnet_link->m_network_links[LinkDirection_Out];
    net_link->setType(EXT_OUT_);
    CreditLink* credit_link = garnet_link->m_credit_links[LinkDirection_Out];

    m_networklinks.push_back(net_link);
    m_creditlinks.push_back(credit_link);

    PortDirection src_outport_dirn = "Local";

    m_max_vcs_per_vnet = std::max(m_max_vcs_per_vnet,
                             m_routers[src]->get_vc_per_vnet());

    /*
     * We check if a bridge was enabled at any end of the link.
     * The bridge is enabled if either of clock domain
     * crossing (CDC) or Serializer-Deserializer(SerDes) unit is
     * enabled for the link at each end. The bridge encapsulates
     * the functionality for both CDC and SerDes and is a Consumer
     * object similiar to a NetworkLink.
     *
     * If a bridge was enabled we connect the NI and Routers to
     * bridge before connecting the link. Example, if an external
     * bridge is enabled, we would connect:
     * NI<---NetworkBridge<---GarnetExtLink<----Router
     */
    if (garnet_link->extBridgeEn) {
        DPRINTF(RubyNetwork, "Enable external bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->extNetBridge[LinkDirection_Out];
        m_nis[local_dest]->
            addInPort(n_bridge, garnet_link->extCredBridge[LinkDirection_Out]);
        m_networkbridges.push_back(n_bridge);
    } else {
        m_nis[local_dest]->addInPort(net_link, credit_link);
    }

    if (garnet_link->intBridgeEn) {
        DPRINTF(RubyNetwork, "Enable internal bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->intNetBridge[LinkDirection_Out];
        m_routers[src]->
            addOutPort(src_outport_dirn,
                       n_bridge,
                       routing_table_entry, link->m_weight,
                       garnet_link->intCredBridge[LinkDirection_Out],
                       m_routers[src]->get_vc_per_vnet());
        m_networkbridges.push_back(n_bridge);
    } else {
        m_routers[src]->
            addOutPort(src_outport_dirn, net_link,
                       routing_table_entry,
                       link->m_weight, credit_link,
                       m_routers[src]->get_vc_per_vnet());
    }
}

/*
 * This function creates an internal network link between two routers.
 * It adds both the network link and an opposite credit link.
*/

void
GarnetNetwork::makeInternalLink(SwitchID src, SwitchID dest, BasicLink* link,
                                std::vector<NetDest>& routing_table_entry,
                                PortDirection src_outport_dirn,
                                PortDirection dst_inport_dirn)
{
    GarnetIntLink* garnet_link = safe_cast<GarnetIntLink*>(link);

    // GarnetIntLink is unidirectional
    NetworkLink* net_link = garnet_link->m_network_link;
    net_link->setType(INT_);
    CreditLink* credit_link = garnet_link->m_credit_link;

    m_networklinks.push_back(net_link);
    m_creditlinks.push_back(credit_link);

    m_max_vcs_per_vnet = std::max(m_max_vcs_per_vnet,
                             std::max(m_routers[dest]->get_vc_per_vnet(),
                             m_routers[src]->get_vc_per_vnet()));

    /*
     * We check if a bridge was enabled at any end of the link.
     * The bridge is enabled if either of clock domain
     * crossing (CDC) or Serializer-Deserializer(SerDes) unit is
     * enabled for the link at each end. The bridge encapsulates
     * the functionality for both CDC and SerDes and is a Consumer
     * object similiar to a NetworkLink.
     *
     * If a bridge was enabled we connect the NI and Routers to
     * bridge before connecting the link. Example, if a source
     * bridge is enabled, we would connect:
     * Router--->NetworkBridge--->GarnetIntLink---->Router
     */
    if (garnet_link->dstBridgeEn) {
        DPRINTF(RubyNetwork, "Enable destination bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->dstNetBridge;
        m_routers[dest]->addInPort(dst_inport_dirn, n_bridge,
                                   garnet_link->dstCredBridge);
        m_networkbridges.push_back(n_bridge);
    } else {
        m_routers[dest]->addInPort(dst_inport_dirn, net_link, credit_link);
    }

    if (garnet_link->srcBridgeEn) {
        DPRINTF(RubyNetwork, "Enable source bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->srcNetBridge;
        m_routers[src]->
            addOutPort(src_outport_dirn, n_bridge,
                       routing_table_entry,
                       link->m_weight, garnet_link->srcCredBridge,
                       m_routers[dest]->get_vc_per_vnet());
        m_networkbridges.push_back(n_bridge);
    } else {
        m_routers[src]->addOutPort(src_outport_dirn, net_link,
                        routing_table_entry,
                        link->m_weight, credit_link,
                        m_routers[dest]->get_vc_per_vnet());
    }
}

// Total routers in the network
int
GarnetNetwork::getNumRouters()
{
    return m_routers.size();
}

// Get ID of router connected to a NI.
int
GarnetNetwork::get_router_id(int global_ni, int vnet)
{
    NodeID local_ni = getLocalNodeID(global_ni);

    return m_nis[local_ni]->get_router_id(vnet);
}

void
GarnetNetwork::regStats()
{
    Network::regStats();

    // Packets
    m_packets_received
        .init(m_virtual_networks)
        .name(name() + ".packets_received")
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    m_packets_injected
        .init(m_virtual_networks)
        .name(name() + ".packets_injected")
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    m_packet_network_latency
        .init(m_virtual_networks)
        .name(name() + ".packet_network_latency")
        .flags(statistics::oneline)
        ;

    m_packet_queueing_latency
        .init(m_virtual_networks)
        .name(name() + ".packet_queueing_latency")
        .flags(statistics::oneline)
        ;

    for (int i = 0; i < m_virtual_networks; i++) {
        m_packets_received.subname(i, csprintf("vnet-%i", i));
        m_packets_injected.subname(i, csprintf("vnet-%i", i));
        m_packet_network_latency.subname(i, csprintf("vnet-%i", i));
        m_packet_queueing_latency.subname(i, csprintf("vnet-%i", i));
    }

    m_avg_packet_vnet_latency
        .name(name() + ".average_packet_vnet_latency")
        .flags(statistics::oneline);
    m_avg_packet_vnet_latency =
        m_packet_network_latency / m_packets_received;

    m_avg_packet_vqueue_latency
        .name(name() + ".average_packet_vqueue_latency")
        .flags(statistics::oneline);
    m_avg_packet_vqueue_latency =
        m_packet_queueing_latency / m_packets_received;

    m_avg_packet_network_latency
        .name(name() + ".average_packet_network_latency");
    m_avg_packet_network_latency =
        sum(m_packet_network_latency) / sum(m_packets_received);

    m_avg_packet_queueing_latency
        .name(name() + ".average_packet_queueing_latency");
    m_avg_packet_queueing_latency
        = sum(m_packet_queueing_latency) / sum(m_packets_received);

    m_avg_packet_latency
        .name(name() + ".average_packet_latency");
    m_avg_packet_latency
        = m_avg_packet_network_latency + m_avg_packet_queueing_latency;

    // Phase 6: per-criticality packet network latency (HC vs LC).
    m_hc_packets_received
        .name(name() + ".hc_packets_received");
    m_hc_packet_network_latency
        .name(name() + ".hc_packet_network_latency");
    m_lc_packets_received
        .name(name() + ".lc_packets_received");
    m_lc_packet_network_latency
        .name(name() + ".lc_packet_network_latency");
    m_avg_hc_packet_network_latency
        .name(name() + ".average_hc_packet_network_latency");
    m_avg_hc_packet_network_latency =
        m_hc_packet_network_latency / m_hc_packets_received;
    m_avg_lc_packet_network_latency
        .name(name() + ".average_lc_packet_network_latency");
    m_avg_lc_packet_network_latency =
        m_lc_packet_network_latency / m_lc_packets_received;

    // Flits
    m_flits_received
        .init(m_virtual_networks)
        .name(name() + ".flits_received")
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    m_flits_injected
        .init(m_virtual_networks)
        .name(name() + ".flits_injected")
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    m_flit_network_latency
        .init(m_virtual_networks)
        .name(name() + ".flit_network_latency")
        .flags(statistics::oneline)
        ;

    m_flit_queueing_latency
        .init(m_virtual_networks)
        .name(name() + ".flit_queueing_latency")
        .flags(statistics::oneline)
        ;

    for (int i = 0; i < m_virtual_networks; i++) {
        m_flits_received.subname(i, csprintf("vnet-%i", i));
        m_flits_injected.subname(i, csprintf("vnet-%i", i));
        m_flit_network_latency.subname(i, csprintf("vnet-%i", i));
        m_flit_queueing_latency.subname(i, csprintf("vnet-%i", i));
    }

    m_avg_flit_vnet_latency
        .name(name() + ".average_flit_vnet_latency")
        .flags(statistics::oneline);
    m_avg_flit_vnet_latency = m_flit_network_latency / m_flits_received;

    m_avg_flit_vqueue_latency
        .name(name() + ".average_flit_vqueue_latency")
        .flags(statistics::oneline);
    m_avg_flit_vqueue_latency =
        m_flit_queueing_latency / m_flits_received;

    m_avg_flit_network_latency
        .name(name() + ".average_flit_network_latency");
    m_avg_flit_network_latency =
        sum(m_flit_network_latency) / sum(m_flits_received);

    m_avg_flit_queueing_latency
        .name(name() + ".average_flit_queueing_latency");
    m_avg_flit_queueing_latency =
        sum(m_flit_queueing_latency) / sum(m_flits_received);

    m_avg_flit_latency
        .name(name() + ".average_flit_latency");
    m_avg_flit_latency =
        m_avg_flit_network_latency + m_avg_flit_queueing_latency;


    // Hops
    m_avg_hops.name(name() + ".average_hops");
    m_avg_hops = m_total_hops / sum(m_flits_received);

    // Links
    m_total_ext_in_link_utilization
        .name(name() + ".ext_in_link_utilization");
    m_total_ext_out_link_utilization
        .name(name() + ".ext_out_link_utilization");
    m_total_int_link_utilization
        .name(name() + ".int_link_utilization");
    m_average_link_utilization
        .name(name() + ".avg_link_utilization");
    m_average_vc_load
        .init(m_virtual_networks * m_max_vcs_per_vnet)
        .name(name() + ".avg_vc_load")
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    // Traffic distribution
    for (int source = 0; source < m_routers.size(); ++source) {
        m_data_traffic_distribution.push_back(
            std::vector<statistics::Scalar *>());
        m_ctrl_traffic_distribution.push_back(
            std::vector<statistics::Scalar *>());

        for (int dest = 0; dest < m_routers.size(); ++dest) {
            statistics::Scalar *data_packets = new statistics::Scalar();
            statistics::Scalar *ctrl_packets = new statistics::Scalar();

            data_packets->name(name() + ".data_traffic_distribution." + "n" +
                    std::to_string(source) + "." + "n" + std::to_string(dest));
            m_data_traffic_distribution[source].push_back(data_packets);

            ctrl_packets->name(name() + ".ctrl_traffic_distribution." + "n" +
                    std::to_string(source) + "." + "n" + std::to_string(dest));
            m_ctrl_traffic_distribution[source].push_back(ctrl_packets);
        }
    }
}

void
GarnetNetwork::collateStats()
{
    RubySystem *rs = params().ruby_system;
    double time_delta = double(curCycle() - rs->getStartCycle());

    for (int i = 0; i < m_networklinks.size(); i++) {
        link_type type = m_networklinks[i]->getType();
        int activity = m_networklinks[i]->getLinkUtilization();

        if (type == EXT_IN_)
            m_total_ext_in_link_utilization += activity;
        else if (type == EXT_OUT_)
            m_total_ext_out_link_utilization += activity;
        else if (type == INT_)
            m_total_int_link_utilization += activity;

        m_average_link_utilization +=
            (double(activity) / time_delta);

        std::vector<unsigned int> vc_load = m_networklinks[i]->getVcLoad();
        for (int j = 0; j < vc_load.size(); j++) {
            m_average_vc_load[j] += ((double)vc_load[j] / time_delta);
        }
    }

    // Ask the routers to collate their statistics
    for (int i = 0; i < m_routers.size(); i++) {
        m_routers[i]->collateStats();
    }
}

void
GarnetNetwork::resetStats()
{
    for (int i = 0; i < m_routers.size(); i++) {
        m_routers[i]->resetStats();
    }
    for (int i = 0; i < m_networklinks.size(); i++) {
        m_networklinks[i]->resetStats();
    }
    for (int i = 0; i < m_creditlinks.size(); i++) {
        m_creditlinks[i]->resetStats();
    }
}

void
GarnetNetwork::print(std::ostream& out) const
{
    out << "[GarnetNetwork]";
}

void
GarnetNetwork::update_traffic_distribution(RouteInfo route)
{
    int src_node = route.src_router;
    int dest_node = route.dest_router;
    int vnet = route.vnet;

    if (m_vnet_type[vnet] == DATA_VNET_)
        (*m_data_traffic_distribution[src_node][dest_node])++;
    else
        (*m_ctrl_traffic_distribution[src_node][dest_node])++;
}

bool
GarnetNetwork::functionalRead(Packet *pkt, WriteMask &mask)
{
    bool read = false;
    for (unsigned int i = 0; i < m_routers.size(); i++) {
        if (m_routers[i]->functionalRead(pkt, mask))
            read = true;
    }

    for (unsigned int i = 0; i < m_nis.size(); ++i) {
        if (m_nis[i]->functionalRead(pkt, mask))
            read = true;
    }

    for (unsigned int i = 0; i < m_networklinks.size(); ++i) {
        if (m_networklinks[i]->functionalRead(pkt, mask))
            read = true;
    }

    for (unsigned int i = 0; i < m_networkbridges.size(); ++i) {
        if (m_networkbridges[i]->functionalRead(pkt, mask))
            read = true;
    }

    return read;
}

uint32_t
GarnetNetwork::functionalWrite(Packet *pkt)
{
    uint32_t num_functional_writes = 0;

    for (unsigned int i = 0; i < m_routers.size(); i++) {
        num_functional_writes += m_routers[i]->functionalWrite(pkt);
    }

    for (unsigned int i = 0; i < m_nis.size(); ++i) {
        num_functional_writes += m_nis[i]->functionalWrite(pkt);
    }

    for (unsigned int i = 0; i < m_networklinks.size(); ++i) {
        num_functional_writes += m_networklinks[i]->functionalWrite(pkt);
    }

    return num_functional_writes;
}

} // namespace garnet
} // namespace ruby
} // namespace gem5

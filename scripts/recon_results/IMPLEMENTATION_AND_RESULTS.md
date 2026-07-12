# Runtime-Reconfigurable NoC — As-Implemented Mechanism & Measured Results

Scope: **only what is actually implemented in code and actually measured in
gem5.** No planned/aspirational features. Platform: gem5 Garnet, `CustomMesh`
8×8 (64 routers), MESI two-level, branch `CustomRouting_v2`. All latencies are
average **packet network latency** in gem5 ticks (1 cycle = 1000 ticks @ 1 GHz).

Legend: **[C]** = committed; **[U]** = implemented this session, uncommitted.

---

## 1. Implemented mechanism

### 1.1 Criticality tag [C]
- `RouteInfo.is_hc` (`CommonTypes.hh`) carried on every Garnet `flit`; set at
  flitisization (`NetworkInterface.cc`) from the encapsulated Ruby
  `Message` criticality. SLICC shadow-field fix: base `Message::getCriticality()`
  made virtual + codegen override for message types with a `crit` field.

### 1.2 Express routing (`routing_algorithm = 2`) [C]
- `RoutingUnit::outportComputeCustom`: for a flit at router `r`, dimension-order
  dimension `d`, remaining offset `Δ_d = |dst_d − cur_d|`, the **2-hop express
  outport in dimension d** is chosen iff:
  `m_express_active(r) ∧ is_hc(flit) ∧ (Δ_d ≥ 2)`.
  Otherwise the ordinary single-hop XY step is taken.
- Express ports used: `TwoHopEast/West` (X phase), `TwoHopNorth/South` (Y phase).
  **Diagonal links are NOT used.** LC flits and the escape path always use the
  base mesh. Strictly dimension-ordered ⇒ minimal, loop-free, deadlock-free for
  **any** subset of active express ports (no escape VC required).
- Express links exist physically at build (`custom_mesh.py`, weight 100); the
  activation flag only admits/masks the express outport in route compute.

### 1.3 Per-router activation flag [C]
- `RoutingUnit::m_express_active` (default false ⇒ custom routing == XY exactly).
- `Router::setExpressActive/getExpressActive`;
  `GarnetNetwork::setAllExpressActive`, `setRouterExpressActive`, init param
  `express_active`.

### 1.4 Reconfiguration manager `reconfigStep()` [C core; policies 1–4 U]
Scheduled by `GarnetNetwork::startup()` every `reconfig_epoch` cycles (fires if
`reconfig_enable ∨ mc_merge_enable`). Each epoch it sweeps all routers, reads
per-router counters (read-and-reset), then actuates per `reconfig_policy`.

Counters (`Router`, incremented in `route_compute`):
- `m_epoch_flit_count` — **all** flits through the router (`consumeEpochFlitCount`).
- `m_epoch_hc_flits`, `m_epoch_lc_flits` — split by `is_hc`. **[U] now counted at
  every router** (was MC-only) so they can be summed network-wide.

**Policy 0 — per-router flit hysteresis (the shipped Phase-4 manager) [C].**
Decision uses **only** `c_r = m_epoch_flit_count` and the previous state:
```
a_r(k) = 1                 if c_r(k) ≥ W_hi          (reconfig_high_wm, def 400)
       = 0                 if c_r(k) ≤ W_lo          (reconfig_low_wm,  def 150)
       = a_r(k-1)          otherwise (hysteresis band)
```
No occupancy, no queue latency, no per-link utilisation, no criticality split.
`c_r` is HC+LC aggregate.

**Policy 1 — global HC-onset [U].** `H(k)=Σ_r m_epoch_hc_flits`; one broadcast
bit via `setAllExpressActive`, same hysteresis with `reconfig_hc_hi/hc_lo`.

**Policy 2 — predictive EWMA + leading edge + hold [U].**
```
m(k)=(1-α)m(k-1)+α·H(k);  σ(k)=H(k)-m(k)
onset = (H≥hc_hi) ∨ (σ≥slope_hi)
onset → hold τ=hold_epochs;  else τ--
express_on = onset ∨ (τ>0);  release when ¬onset ∧ τ=0 ∧ H≤hc_lo
```
Params `reconfig_ewma_alpha` (0.5), `reconfig_slope_hi` (40),
`reconfig_hold_epochs` (8). Thresholds calibrated **offline** (MFDFA, in the
eval script — not in gem5).

**Policy 3 — RL tabular Q-learning [U].**
- State (36) = `(demand_bin×3, slope_sign×2, recency_since_burst×3, express_bit×2)`.
- Action = express all-on / all-off.
- Reward `r = −( Q_HC/κ + λ·express_on )`, `Q_HC = Σ_r getHcQueuedFlits()`
  (occupancy of VCs whose head flit is HC), `κ=reconfig_rl_occ_scale`.
- `Q(s,a) += η[r + γ·max_a' Q(s',a') − Q(s,a)]`, ε-greedy while training.
- Train (`rl_train=1`): ε-greedy + TD updates, Q-table dumped to `q_file`.
  Deploy (`rl_train=0`): load Q, greedy, frozen. Params lr 0.2/eps 0.2/gamma
  0.9/lambda 0.5/occ_scale 100/seed 1.

**Policy 4 — oracle periodic schedule [U].** Perfect burst foreknowledge:
`express_on = (φ<On) ∨ ((φ+L)%P<On)`, `φ=(t−start)%P`. Params
`reconfig_sched_start/period/on/lead` (ticks). Upper-bound reference only.

### 1.5 MC-router elastic VC merge (Phase 7) [C]
- `mc_router_ids` = Directory routers (21, 42). Per-criticality VC partition at
  MC only (`SwitchAllocator::critVcRange`): HC→VC{0,1} (VC0 escape), LC→VC{2,3};
  `OutputUnit::has_free_vc/select_free_vc` take offset windows.
- Dynamic merge: `Router::m_vc_merge_active` widens HC window to full range when
  armed; two-factor gate in `reconfigStep`: arm iff `hc≥mc_hc_hi ∧ lc≤mc_lc_lo`,
  disarm otherwise. Params `mc_merge_enable/mc_hc_hi/mc_lc_lo`.

### 1.6 Instrumentation [U]
- `ReconTrace` debug flag (`src/mem/ruby/SConscript`) → per-router per-epoch
  `RTRACE` line: `flits, mc, hc, lc, hcocc, dnocc, ex`.
- `Router::getCritVcOccupancy` (HC=low-half VCs, donor=high-half),
  `getTotalOccupancy`, `getHcQueuedFlits`.
- Per-criticality latency stats (`average_hc/lc_packet_network_latency`) [C].

### 1.7 Workload harness (`configs/network/recon_traffic.py`) [C + U]
- `MixedRateLinearGenerator`: 64 linear cores, HC subset at `--hc-rate`, rest at
  `--lc-rate`.
- `BurstyGeneratorCore` [U]: HC cores stream `--hc-burst` ON / `--hc-gap` OFF,
  repeating, with optional `--hc-warmup` leading idle. LC steady background.

---

## 2. Measured results (real gem5 output)

### 2.1 Static vs runtime express — original congested load [C]
HC minority 8/64, 2 GiB/s each, 0.05 ms, `recon_eval.py`:

| scheme | HC net latency | LC net latency |
|---|---|---|
| baseline (XY) | reference | reference |
| **static-all express** | **−27.9%** | **+1.8%** |
| runtime manager (Policy 0) | −3.7% … −10% | ~flat |

Static express meets the goal; the Policy-0 runtime manager is much weaker.

### 2.2 Root cause of weak runtime benefit — congestion collapse [U]
Sustained load, HC srcs 8/64, 8 GiB/s, 0.03 ms, epoch 100:

- Init-active express → HC ≈ 26 k; runtime-activated (same links, same routing,
  identical hops, express *is* used) → HC ≈ 42 k ≈ baseline.
- Epoch (activation-delay) sweep, activate-all: 1000→42.7 k, 500→39.9 k,
  100→29.8 k, **20→27.0 k ≈ static**.
- HC-rate sweep 2→16 GiB/s: runtime HC vs baseline flat (+1.2% … −1.7%).

Conclusion: mesh congestion-collapses within ~100 cycles; reactive activation
that fires after collapse cannot drain the backlog. Init/early activation
prevents it. ⇒ elastic saving requires **bursty** load; needs fine epoch.

### 2.3 Elastic reactive vs predictive — bursty load [U]
HC burst 2000 ns / gap 3000 ns / warmup 5000 ns, 8 GiB/s, 0.05 ms, epoch 100:

| scheme | HC latency | express duty |
|---|---|---|
| baseline | 33442 | 0% |
| static-all | 26426 | 100% |
| **reactive-global (P1)** | **26991** | **40%** |
| MFDFA-predictive (P2) | 27112 | 57% |

Reactive-global ≈ static HC at 40% duty (express off 60% of time). Offline MFDFA
on the real HC series: h(2)=0.85 (persistent), multifractal — confirms
burstiness, but the online slope predictor over-fires ⇒ no gain over reactive.

### 2.4 RL + oracle — sparse bursts, decisive test [U]
HC burst 2000 ns / gap 6000 ns / warmup 5000 ns, 8 GiB/s, 0.1 ms, epoch 100.
Sparse bursts chosen to give prediction maximum headroom.

| controller | HC latency | express duty |
|---|---|---|
| baseline | 35291 | 0% |
| static-all | 27360 | 100% |
| **reactive (P1, feedback)** | **27788** | **42%** |
| MFDFA-predictive (P2) | 27931 | 50% |
| RL Q-learning (P3), any λ | ~35300 | ~0% |
| oracle onset, lead 0 | 34576 | 24% |
| oracle onset, lead 2 µs | 31305 | 47% |
| oracle trailing, on 5 µs | 29612 | 60% |

Figure: `scripts/recon_results/rl/R4_verdict_pareto.png`.

**Findings:**
- Reactive feedback **dominates every** predictive / oracle / RL point.
- A *perfect* onset oracle is worse than reactive; covering exactly the burst
  input window (24% duty) ≈ baseline latency.
- Reason: the express-relief window is **burst + post-burst drain tail**.
  Feedforward schedules cut express at burst-input end and miss the drain; only
  closed-loop feedback tracks it.
- RL collapses to express-off (with total-occupancy reward it saw express as
  pure cost; even with the HC-specific reward it cannot beat reactive because
  partial/anticipatory activation does not cover the drain).

**Answer to “is MFDFA the reason prediction fails”: No.** RL (a stronger
predictor) and a perfect oracle also fail to beat reactive ⇒ prediction has no
headroom here; this is a feedback-control problem with an observable
disturbance. MFDFA is not the root cause, and prediction (MFDFA or RL) is not
the way — reactive feedback is near-optimal.

### 2.5 MC elastic VC merge (Phase 7) [C]
- Static isolation cost measured: HC latency 28221→38259, LC 28260→36819 (fewer
  VCs per class ⇒ more head-of-line blocking).
- Dynamic merge deadlock-free, arms at R21/R42, but **benefit is
  regime-specific** (needs an HC micro-burst saturating HC’s 2 VCs while the LC
  donor is idle). Steady-uniform (donor busy) and LC-light (HC not starved) both
  show no gain. Not demonstrated to pay under the workloads tried.

---

## 3. Bottom line
- **Static** criticality-aware express routing: HC −28% at ~2% LC cost (goal met).
- **Runtime reactive-global** express (Policy 1, fine epoch): matches static HC at
  <½ the express duty cycle — the elastic win.
- **Prediction (MFDFA Policy 2, RL Policy 3) and even a perfect oracle (Policy 4)
  do not beat reactive.** Negative result: prediction is unnecessary; the relief
  window (burst + drain) is best tracked by feedback.
- **Policy 0 (shipped manager) decides on the aggregate flit counter alone** and
  is the weakest — HC+LC-blind and reactive-after-collapse.

## 4. Files & scripts
- Garnet: `RoutingUnit.{cc,hh}`, `Router.{cc,hh}`, `GarnetNetwork.{cc,hh,py}`,
  `SwitchAllocator.cc`, `OutputUnit.{cc,hh}`, `VirtualChannel.hh`,
  `InputUnit.hh`, `flit.{hh,cc}`, `CommonTypes.hh`, `src/mem/ruby/SConscript`.
- Hierarchy/config: `mesi_two_level_cache_network.py`, `custom_mesh.py`,
  `configs/network/recon_traffic.py`.
- Eval: `recon_eval.py` (static/reconfig), `recon_motivation.py`,
  `recon_predictive.py` (MFDFA), `recon_rl.py` (RL train/deploy),
  `recon_verdict.py` (combined Pareto). Outputs under `scripts/recon_results/`.

# Coverage-Guided Adversarial Trace-Flow Generation for Mixed-Criticality NoC Certification and Design-Space Optimization

Self-contained implementation plan for a gem5/Garnet research artifact. No external plan files.

## 1. Research Thesis

Mixed-criticality systems (MCS) co-host high-criticality (HC) flows — governed by certification
standards such as ISO 26262 (automotive ASIL) or DO-178C / ARINC 653 (avionics) — with
low-criticality (LC) best-effort flows on one shared Network-on-Chip. Certification requires a
**bounded worst-case communication latency (WCL)** for every HC flow that holds under *any*
admissible LC behavior.

Two standard methodologies are inadequate:

- **Static WCL/WCET analysis** is sound but pessimistic; the analytical bound is loose, wasting NoC
  resources and over-constraining the design.
- **Fixed synthetic + random traffic** (uniform, transpose, tornado, neighbor, shuffle,
  bit-complement) is optimistic; it undersamples the adversarial LC interference patterns that
  actually maximize HC latency.

**Central claim:** a *coverage-guided, criticality-aware trace-flow generator* automatically searches
the LC-interference space for the pattern that maximizes HC flow latency — the **empirical
worst-case latency (eWCL) witness** — producing (a) certification evidence, (b) a robustness-labeled
configuration corpus, and (c) a worst-case-isolation ranking that changes which NoC configurations
and isolation mechanisms are judged "safe-optimal."

The contribution is methodological, not merely a new fuzzer algorithm.

## 2. Three Roles

| Role | Output | Result to target |
|---|---|---|
| **R1 — Certification witness tool** | Deterministic, replayable LC trace that drives a fixed HC flow past its deadline / interference bound | Find a violating witness Nx faster than random / Monte-Carlo search; expose configs that *look* safe under fixed traffic |
| **R2 — Curation engine** | Robustness-labeled corpus of (config, eWCL, isolation-score) tuples; certified-safe config set | Build a labeled DSE dataset cheaper than exhaustive sweep; reusable artifact |
| **R3 — DSE / test-time oracle** | Per-config **Isolation Robustness Score**; Pareto front (avg performance vs certified worst-case isolation) | Rank inversions: a config optimal on fixed traffic is unsafe under fuzzed traffic |

## 3. Novel Metrics

- **eWCL (empirical worst-case latency)** of an HC flow = max HC latency the fuzzer finds over the
  LC-interference corpus for a fixed config. Empirical *lower bound* on true WCL — not a proof.
- **Interference Tightness Gap** `ITG = eWCL_found / WCL_analytical`. Near 1 → tight static bound;
  ≪ 1 → static analysis pessimistic, design wastes margin. Headline metric.
- **Isolation Robustness Score** `IRS(config) = HC_latency_nominal / worst_HC_latency_over_corpus`.
  Higher = better isolation under adversarial LC. Drives DSE ranking.
- **Criticality-Inversion Count** = events where an LC flit wins arbitration / a VC / a credit over a
  ready HC flit, or an HC flit stalls behind LC occupancy.

## 4. Repository Grounding (verified in this tree)

Entry point and build:
- Driver: `configs/example/garnet_synth_traffic.py`
- Protocol: `Garnet_standalone` (NULL build → `build/NULL/gem5.opt`)
- Network options: `configs/network/Network.py`

Verified CLI flags (these exist; do not assume others):
- From driver: `--synthetic`, `--injectionrate`, `--inj-vnet`, `--single-sender-id`,
  `--single-dest-id`, `--num-packets-max`, `--sim-cycles`, `--precision`
- From network: `--network`, `--topology`, `--mesh-rows`, `--routing-algorithm`,
  `--vcs-per-vnet`, `--link-latency`, `--router-latency`, `--link-width-bits`,
  `--garnet-deadlock-threshold`, `--network-fault-model`

Important correction: **buffer depth is NOT a CLI flag here.** `buffers_per_data_vc` (default 4) and
`buffers_per_ctrl_vc` (default 1) are SimObject params in
`src/mem/ruby/network/garnet/GarnetNetwork.py` only. To sweep buffer depth in DSE you must add a CLI
option in `configs/network/Network.py` that sets these params, or edit the defaults per run.

`routing-algorithm` encoding (`GarnetNetwork.py`): `0` = weight-based table, `1` = XY, `2` = Custom.

Traffic generator SimObject params (`src/cpu/testers/garnet_synthetic_traffic/`):
`GarnetSyntheticTraffic.py` exposes `traffic_type`, `inj_rate`, `inj_vnet`, `single_sender`,
`single_dest`, `num_dest` (default 1), `sim_cycles`, `num_packets_max`. Logic lives in
`GarnetSyntheticTraffic.cc`.

Garnet C++ hook points for instrumentation:
- `InputUnit.cc` — VC buffering + route-compute entry; sample input-buffer occupancy; record
  `(src_router, dst_router, inport, outport)` on HEAD/HEAD_TAIL.
- `SwitchAllocator.cc` — `send_allowed` (why a flit cannot advance: no free out-VC, no credit,
  ordered-vnet block) and `arbitrate_*` (winners/losers per outport). Primary site for
  criticality-inversion detection.
- `NetworkLink.cc` — `m_link_utilized`, `m_vc_load` totals; add windowed buckets.
- `NetworkInterface.cc` — latency accounting; split histograms by criticality class.
- `GarnetNetwork.{hh,cc}` — own a shared coverage collector.
- `RoutingUnit.cc` — `routing-algorithm=2` Custom path; site for criticality-aware routing.
- `flit.hh` — flit metadata (route, vnet, vc, hops, latency); target field for a criticality tag.

Topologies present in `configs/topologies/`: `Mesh_XY`, `Mesh_westfirst`, `MeshDirCorners_XY`,
`CustomMesh`, `Crossbar`, `CrossbarGarnet`, `Pt2Pt`.

## 5. Criticality Representation — two options

- **Reserved-vnet convention (MVP, zero C++):** designate one vnet (or a VC range) as the HC class;
  treat all traffic on it as HC. The HC flow is a fixed `--single-sender-id` → `--single-dest-id`
  flow on `--inj-vnet = <HC vnet>`. LC = everything else. Enough to prove the research signal.
- **First-class criticality tag (paper-strength):** add `m_criticality` to `flit.hh`, set it at
  injection in `GarnetSyntheticTraffic.cc` / `NetworkInterface.cc`, propagate, and read it in
  `SwitchAllocator.cc` / `RoutingUnit.cc`. Required for true inversion detection and crit-aware
  isolation mechanisms.

## 6. Isolation Mechanism (system-under-test)

Pick at least one mechanism whose worth the fuzzer will quantify under adversarial (not average) LC:
- HC/LC **VC partitioning** — disjoint VC sets per criticality (`SwitchAllocator.cc`/`OutputUnit.cc`).
- **HC priority arbitration** — HC wins switch/VC arbitration (`SwitchAllocator::arbitrate_*`).
- **Criticality-aware routing** — `routing-algorithm=2` in `RoutingUnit.cc`.

Each is a binary (on/off) axis in the DSE search; the headline safety result is that turning a
mechanism on collapses eWCL / raises IRS under fuzzed LC.

## 7. Artifact Layout

```
tools/fuzzer/
  orchestrator.py     # launch gem5 runs, record metadata, parallel exec
  traffic_schema.py   # structured criticality-tagged seed/corpus format
  mutators.py         # LC-interference mutation operators
  selection.py        # eWCL/coverage-prioritized seed selection
  dse.py              # outer-loop DSE driver
  stats_parser.py     # parse stats.txt + per-criticality split + coverage JSON
tools/coverage/
  engine.py           # coverage-vector build, diff, acceptance
  buckets.py          # occupancy / util / latency / stall / inversion buckets
  analysis.py         # corpus summary, Pareto front, ranking deltas, ITG/IRS
experiments/mcs_noc/
  configs/            # YAML experiment definitions
  corpus/             # accepted criticality-tagged seeds
  runs/               # per-run cmd, stdout/stderr, stats, coverage JSON
  results.db          # SQLite for reproducibility + querying
src/mem/ruby/network/garnet/
  GarnetCoverage.{hh,cc}   # new collector (add to SConscript), guarded by param
```

## 8. Phased Plan

### Phase 0 — MCS Baseline (no C++)
- HC flow = fixed `--single-sender-id S --single-dest-id D --inj-vnet H` on the reserved HC vnet.
- LC background = standard `--synthetic` patterns at rising `--injectionrate`.
- Record HC flow latency vs LC load. Establishes nominal HC latency + a *fixed-traffic* worst case to
  beat.
- Example run shape:
  ```bash
  build/NULL/gem5.opt configs/example/garnet_synth_traffic.py \
    --network=garnet --topology=Mesh_XY --mesh-rows=4 \
    --num-cpus=16 --num-dirs=16 \
    --synthetic=uniform_random --injectionrate=0.1 \
    --sim-cycles=10000 --vcs-per-vnet=4 --routing-algorithm=1
  ```
- Exit: reproducible HC-latency-under-LC-load curves; DB stores (config, HC flow, LC pattern, HC
  latency, LC latency, git hash, seed id).

### Phase 1 — Safety-State Coverage Engine
- Coverage vector = sparse set of bucket IDs. MCS dimensions on top of generic ones:
  - Criticality-inversion buckets (HC flit blocked by / loses to LC at `(router,inport,outport)`).
  - HC deadline-adjacency (HC flow latency within X% of its deadline budget).
  - Isolation-violation states (HC flit waits on a VC/credit held by LC).
  - Generic support: VC occupancy, link utilization, stall-reason, tail-latency buckets.
- Implement `GarnetCoverage.{hh,cc}`, add to `SConscript`, guard with new `enable_coverage` /
  `coverage_output` params in `GarnetNetwork.py` + matching CLI in `Network.py`. Emit line-delimited
  JSON (parseable, not debug text).
- MVP fallback: derive inversion/adjacency proxies from existing per-vnet stats before writing C++.
- Exit: hand-crafted LC hotspot near the HC path raises inversion + adjacency buckets; coverage
  stable for identical seeds.

### Phase 2 — Criticality-Aware Trace Seeds
- Seed schema, one protected HC flow held fixed; only LC mutates:
  ```json
  {
    "seed_id": "seed_000142",
    "num_nodes": 16,
    "duration_cycles": 10000,
    "flows": [
      {"src": 0, "dst": 15, "vnet": 2, "criticality": "HC",
       "start": 0, "stop": 10000, "rate": 0.05},
      {"src": 3, "dst": 12, "vnet": 0, "criticality": "LC",
       "start": 100, "stop": 9000, "rate": 0.4,
       "burst": {"period": 500, "on": 80, "rate": 0.8}}
    ]
  }
  ```
- MVP: orchestrator maps each seed onto existing CLI knobs (`--single-sender-id`,
  `--single-dest-id`, `--inj-vnet`, `--injectionrate`). Paper-strength: extend
  `GarnetSyntheticTraffic.cc` to read the seed file and make per-node/per-phase injection decisions.
- LC-interference mutation operators (HC flow immutable):
  - LC-rate / LC-hotspot around HC source, sink, and HC path links.
  - Phase-offset to align LC bursts with HC injection (transient contention).
  - VC-contention forcing LC onto VCs the HC flow needs.
  - Bisection / corner crossing the HC route.
- Exit: every accepted seed replays HC latency within tolerance; HC flow provably fixed; corpus
  format is simulator-independent enough to be a reusable artifact.

### Phase 3 — eWCL Witness Fuzzer (R1)
- Inner loop maximizes HC latency / inversion under a fixed simulation budget.
  1. Select parent. 2. Mutate LC into child. 3. Run gem5. 4. Parse stats + coverage.
  5. Score. 6. Accept if it raises eWCL, hits new safety buckets, or improves the
     coverage-efficiency frontier.
- Objective:
  ```
  stress(child) = w1*hc_latency_excursion + w2*criticality_inversion_count
                + w3*deadline_adjacency  + w4*new_safety_buckets
                - w5*redundancy_penalty
  accept(child) = (new_bucket_count >= tau_cov) OR (stress >= tau_stress)
                  OR improves coverage-efficiency frontier
  ```
- Controls (matched budget): random LC mutation, fixed synthetic LC only, Monte-Carlo LC sampling.
- Exit: fuzzer reaches higher eWCL with fewer simulations than every control; report
  speedup-to-first-violation, eWCL-vs-budget, ITG per config; witness is human-interpretable
  (e.g., "synchronized LC burst on the HC bisection link").

### Phase 4 — Curation + DSE Re-ranking (R2, R3)
- Search axes: topology (`Mesh_XY`, `Mesh_westfirst`, `MeshDirCorners_XY`, `CustomMesh`), routing
  (`0/1/2`), `--vcs-per-vnet` ∈ {2,4,8}, link/router latency, buffer depth (needs new CLI per §4),
  and **isolation mechanism on/off** (§6).
- Per config: avg/p99 latency, eWCL(HC), ITG, IRS, criticality-inversion rate.
- Core results:
  1. Rank configs under fixed vs fuzzed traffic → report rank inversions (safe-looking config that
     fails under fuzzed LC).
  2. Pareto front: avg performance vs IRS.
  3. Enabling an isolation mechanism collapses eWCL / raises IRS under adversarial LC — quantifies
     its safety value beyond average-case.
- Artifact: robustness-labeled (config, eWCL, IRS) dataset + certified-safe config set.
- Exit: ≥1 convincing rank inversion; Pareto front; statistical confidence over repeated seeds with
  matched budgets.

### Phase 5 — Validation & Ablation
- Ground-truth witness: a hand-built LC adversary on the HC path should be matched or beaten by the
  fuzzed witness.
- Replay determinism: accepted witnesses reproduce eWCL within tolerance.
- Instrumentation overhead: coverage on vs off runtime.
- Ablate each MCS coverage dimension; ablate each LC mutation family; coverage-guided vs random
  parent selection.
- Threats to validity: synthetic LC ≠ real workloads; coverage metric gaming; Garnet lacks
  area/power; results depend on mesh size / routing; instrumentation must not perturb NoC semantics.
  **Soundness:** eWCL is an empirical lower bound on true WCL — state this; the contribution is
  tightening the gap and exposing optimistic configs, not replacing formal WCL analysis.

## 9. Minimum Viable Prototype (cheap signal)
1. Reserved-vnet HC convention — no C++.
2. Fixed HC flow + LC synthetic background sweep (Phase 0).
3. Coverage from existing stats: HC latency buckets, LC load buckets, inversion proxy from per-vnet
   latency split.
4. LC-only mutation loop maximizing HC latency.
5. If eWCL rises measurably above the fixed-traffic worst case → signal exists → invest in
   `GarnetCoverage` C++ and a first-class criticality tag.

## 10. Paper Structure
1. Introduction — MCS NoC certification needs adversarial interference evidence; static = pessimistic,
   random = optimistic.
2. Background — MCS NoC, WCL analysis, isolation mechanisms, coverage-guided fuzzing.
3. Motivation — a config certified-safe under fixed traffic misses an LC witness that violates the HC
   deadline.
4. Method — criticality-aware trace seeds, safety-state coverage vector, LC-interference mutations,
   eWCL-maximizing selection, acceptance policy.
5. Implementation — Garnet hooks, criticality tagging, isolation mechanisms, experiment DB, replay.
6. Evaluation — ITG tightening, witness-discovery speedup vs random/Monte-Carlo, DSE re-ranking, IRS
   Pareto, isolation-mechanism value.
7. Ablation — coverage dimensions, mutation families, search policy.
8. Discussion — relation to formal WCL, real traces, limits.
9. Conclusion.

## 11. Immediate Next Steps
1. Choose criticality representation: reserved-vnet convention (start here) vs first-class flit tag.
2. Choose ≥1 isolation mechanism as the system-under-test.
3. Build `tools/fuzzer/orchestrator.py`: pin one HC flow, sweep LC background, store run metadata +
   raw `stats.txt` (Phase 0).
4. Build `tools/fuzzer/stats_parser.py` with per-vnet (HC vs LC) latency split.
5. Run the MVP eWCL loop; confirm fuzzed LC raises HC latency above the fixed-traffic worst case.
6. Only then build `GarnetCoverage` and the first-class criticality tag.

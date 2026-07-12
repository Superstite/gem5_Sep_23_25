# Consolidated Results — Runtime-Reconfigurable NoC (all real gem5 output)

Latencies = average **packet network latency** (ticks; 1 cycle = 1000 ticks @ 1 GHz).
"duty" = % of router-epochs with express active.

## Common setup
- gem5 Garnet, `CustomMesh` 8×8 = 64 tiles, MESI two-level, DDR4, 4 VCs/vnet.
- 64 `LinearGenerator` cores, block 64 B, 100% reads. HC source ids =
  {0,3,10,20,29,35,48,59} (8 of 64); rest are LC.
- Influential (MC/Directory) routers = 21, 42. Static per-criticality VC
  isolation at those routers (HC={VC0,1}, donor LC={VC2,3}) is always on.
- `baseline` = XY routing (algo 1), express never used. Others use custom
  express routing (algo 2).

## Traffic workloads
| id | description | HC rate | LC rate | duration | epoch |
|----|---|---|---|---|---|
| W1 | steady, original congested | 2 GiB/s | 2 GiB/s | 0.05 ms | 5000 |
| W2 | steady sustained (collapse / saturation) | 2–16 GiB/s | 2 GiB/s | 0.03 ms | 20–1000 |
| W3 | **bursty** HC 2000 ns on / 3000 ns off, 5000 ns warmup | 8 GiB/s | 2 GiB/s | 0.05 ms | 100 |
| W4 | **sparse bursty** HC 2000 ns on / 6000 ns off, 5000 ns warmup | 8 GiB/s | 2 GiB/s | 0.1 ms | 100 |
| W5 | sparse bursty HC + **light LC** (merge test) | 8 GiB/s | 0.2 GiB/s | 0.1 ms | 100 |

---

## A. Static vs runtime express — W1 (steady) [`eval.csv`]
| scheme | HC lat | LC lat |
|---|---|---|
| baseline | 28221 | 28260 |
| static-all express | **20358 (−27.9%)** | 28764 (+1.8%) |
| runtime reconfig (Policy 0) | 27191 (−3.7%) | 28302 |

Static express meets the goal; the per-router Policy-0 manager is weak.

## B. Root cause — congestion collapse (activation delay), W2, HC 2 GiB/s
Activate-all express, vary epoch = activation delay. baseline 47681, static 26165.
| epoch (delay) | HC lat |
|---|---|
| 1000 | 42668 |
| 500 | 39872 |
| 100 | 29773 |
| 20 | 26962 |
| express active at init | 26425 |

Runtime activation must fire inside the ~100-cycle collapse window; init/early
activation recovers the static benefit. Mechanism works — the manager was late.

## C. HC saturation sweep — W2 (0.03 ms, LC 2 GiB/s)
| HC rate | baseline | static-all | reconfig (P0) |
|---|---|---|---|
| 2 GiB/s | 47681 | 26165 | 48265 |
| 4 GiB/s | 43210 | 23624 | 42459 |
| 8 GiB/s | 35487 | 23869 | 35066 |
| 16 GiB/s | 34166 | 23377 | 33940 |

More HC does **not** help the runtime manager (flat vs baseline) — disproves the
"needs more HC" hypothesis; confirms it is the collapse/timing issue.

## D. Elastic reactive vs predictive — W3 (bursty) **[duty-cycle results]**
| scheme | HC lat | LC lat | express duty |
|---|---|---|---|
| baseline | 33442 | 36959 | 0% |
| static-all | 26426 | 37419 | 100% |
| **reactive-global (P1)** | **26986** | 37135 | **40%** |
| MFDFA-predictive (P2) | 27233 | 37241 | 50% |

Reactive elastic ≈ static HC at **40% duty** (express off 60% of time). MFDFA
predictor over-fires → more duty, no HC gain. MFDFA on the real HC series:
h(2)=0.85 (persistent), multifractal — diagnostic only, not an online predictor.

## E. RL + oracle — W4 (sparse bursty) **[duty-cycle results]**
| controller | HC lat | express duty |
|---|---|---|
| baseline | 35291 | 0% |
| static-all | 27360 | 100% |
| **reactive (P1, feedback)** | **27788** | **42%** |
| MFDFA-predictive (P2) | 27931 | 50% |
| RL Q-learning (P3) λ=0.1 | 35784 | 11% |
| RL λ=0.3 | 35617 | 1% |
| RL λ=0.6 / 1.0 | 35291 | 0% |
| oracle onset lead 0 | 34576 | 24% |
| oracle onset lead 1 µs | 32148 | 35% |
| oracle onset lead 2 µs | 31305 | 47% |
| oracle trailing on 4 µs | 31448 | 48% |
| oracle trailing on 5 µs | 29612 | 60% |

**Reactive feedback dominates every predictive / RL / oracle point.** Even a
perfect onset oracle is worse than reactive. Reason: the express-relief window is
burst + post-burst **drain tail**; only closed-loop feedback tracks it.
⇒ Prediction has no headroom; **MFDFA is not the root cause** — it is a
feedback-control problem, not a prediction problem.

## F. Express + elastic VC merging — W5 (light LC so donor can be idle)
| config | HC lat | LC lat |
|---|---|---|
| baseline | 36244 | 32472 |
| **express** | **28031 (−22.7%)** | 32191 |
| express + merge (two-factor gate) | 28031 (**+0**) | 32191 |
| express + merge (gate forced open) | 27263 (−2.7% vs express) | 32264 |

Express activation is the large win. VC merging gives **no** measurable gain under
the real two-factor gate (HC-burst ∧ donor-idle rarely coincide) and only −2.7%
even forced always-on — HC is not strongly VC-starved at the influential routers
in these workloads. Merge is deadlock-safe and arms, but its benefit is marginal.

---

## Bottom line
1. **Static express**: HC −28% at ~2% LC cost (W1).
2. **Runtime reactive-global express** (fine epoch): matches static HC at **<½ the
   express duty** (W3/W4) — the elastic win. Must act inside the collapse window.
3. **Prediction (MFDFA, RL) and even a perfect oracle do not beat reactive** (W4).
4. **VC merging**: marginal (≤2.7%), not demonstrated to pay under tested loads (W5).

## Figures
- `predictive/P1_mfdfa.png`, `predictive/P2_latency_vs_duty.png` (W3 elastic + MFDFA)
- `rl/R4_verdict_pareto.png` (W4 HC-vs-duty Pareto, all controllers)
- `merge/A_merge_disabled.png`, `merge/B_merge_enabled.png`, `merge/C_combined_hc.png` (W5)
- `summary/F1_collapse.png`, `summary/F2_saturation.png`,
  `summary/F3_elastic_duty.png`, `summary/F4_pareto.png` (generated by
  `scripts/gen_all_results.py`)

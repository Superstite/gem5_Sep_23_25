#!/usr/bin/env python3
"""Parse gem5 stats.txt into a flat dict, with helpers for the
mixed-criticality NoC metrics.

Vector stats with subnames (e.g. average_flit_latency_crit::LC) and totals
(e.g. flits_received::total) are flattened to dotted/`::` keys. Only the first
numeric column of each line is taken (the value); pdf/cdf percentage columns
are ignored.

See plans/mcs_trace_flow_plan.md (Phase 0).
"""

from __future__ import annotations

import math
import re

NET_PREFIX = "system.ruby.network."

_num_re = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _to_float(tok: str):
    if tok.lower() in ("nan", "-nan"):
        return math.nan
    if tok.lower() in ("inf", "-inf"):
        return math.inf if tok[0] != "-" else -math.inf
    if _num_re.match(tok):
        return float(tok)
    return None


def parse_stats(path: str) -> dict:
    """Return {stat_name: value}.

    Scalar lines:   name   value   # description
    Vector lines (gem5 `oneline` flag) collapse all buckets onto one line with
    '|'-separated columns:
        name | v0 | v1 | ... # description
    These are exposed positionally as `name::0`, `name::1`, ... so a parser can
    index buckets even though gem5 omits the per-bucket subname there. Separate
    `name::total` / `name::subname` scalar lines are captured as-is.
    """
    stats: dict[str, float] = {}
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("-"):
                continue
            # Drop trailing description: either '# ...' or '(Unit)' marker.
            if "#" in line:
                line = line.split("#", 1)[0].strip()
            if not line:
                continue

            if "|" in line:
                # Vector line. First segment holds the name (+ bucket 0 value).
                segs = line.split("|")
                head = segs[0].split()
                if not head:
                    continue
                name = head[0]
                cols = []
                if len(head) > 1:
                    cols.append(head[1])
                for seg in segs[1:]:
                    toks = seg.split()
                    if toks:
                        cols.append(toks[0])
                for i, tok in enumerate(cols):
                    v = _to_float(tok)
                    if v is not None:
                        stats[f"{name}::{i}"] = v
                continue

            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[0]
            val = _to_float(parts[1])
            if val is not None:
                stats[name] = val
    return stats


def _get(stats: dict, suffix: str, default=math.nan):
    return stats.get(NET_PREFIX + suffix, default)


def criticality_summary(stats: dict) -> dict:
    """Pull the HC vs LC latency / volume metrics out of a parsed stats dict.

    Buckets are positional: index 0 == LC, index 1 == HC (see
    GarnetNetwork::regStats subname order). Returns NaNs / 0 where a class
    produced no traffic (e.g. HC disabled)."""
    return {
        "lc_avg_flit_latency": _get(stats, "average_flit_latency_crit::0"),
        "hc_avg_flit_latency": _get(stats, "average_flit_latency_crit::1"),
        "lc_avg_packet_latency": _get(stats, "average_packet_latency_crit::0"),
        "hc_avg_packet_latency": _get(stats, "average_packet_latency_crit::1"),
        "lc_flits_received": _get(stats, "flits_received_crit::0", 0.0),
        "hc_flits_received": _get(stats, "flits_received_crit::1", 0.0),
        "lc_packets_received": _get(stats, "packets_received_crit::0", 0.0),
        "hc_packets_received": _get(stats, "packets_received_crit::1", 0.0),
    }


def network_summary(stats: dict) -> dict:
    """Aggregate (criticality-agnostic) network metrics used for DSE ranking."""
    return {
        "avg_packet_latency": _get(stats, "average_packet_latency"),
        "avg_flit_latency": _get(stats, "average_flit_latency"),
        "avg_hops": _get(stats, "average_hops"),
        "flits_received_total": _get(stats, "flits_received::total", 0.0),
        "flits_injected_total": _get(stats, "flits_injected::total", 0.0),
        "packets_received_total": _get(stats, "packets_received::total", 0.0),
        "avg_link_utilization": _get(stats, "avg_link_utilization"),
        "sim_ticks": stats.get("simTicks", math.nan),
    }


if __name__ == "__main__":
    import json
    import sys

    s = parse_stats(sys.argv[1])
    print(
        json.dumps({**network_summary(s), **criticality_summary(s)}, indent=2)
    )

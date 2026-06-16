"""
Deterministic ground-truth engine for the sg-deep-lateral-auditor screening harness.

This module REUSES the already-validated reachability engine from the sibling skill
`lateral-movement-reachability-auditor` verbatim. The proven graph/BFS/articulation
logic lives in `_reach_engine.py` (a byte-for-byte copy of that skill's `tests/_reach.py`),
so ground truth here is provably the same computation. We do NOT change the engine.

The only thing this file adds is a thin alias `run_deep(fixture_dir) -> Reachability`
so the screening harness can speak its own verb while computing the identical result.
The returned object exposes the same surface the sibling engine returns:

    .findings        list[Finding]            (P1 path / B1 blast radius / H1 hub)
    .codes()         set[str]
    .top_severity    "critical"|"high"|... | None
    .clean           bool
    .boundary        list[str]
    .shortest_path   list[str]
    .reachable       list[str]   (blast radius, entry excluded)
    .edges           list[tuple[str,str]]

This screening harness is scoped ENTIRELY to the model's empirically-located WEAK
region: LONG (4-6 hop) lateral chains buried in a 10-14 SG fleet, plus deceptive /
segmented-clean fleets where a loud public exposure or a visible-but-orphaned deep
SG-ref chain must NOT be reported as a reachable path to the crown jewel. There are no
short, obvious 2-3 hop direct paths -- those the base model already aces. The "needle"
is the COMPOSITION of many ordinary single-upstream SG-to-SG edges into one long path
that only appears when the whole chain is assembled; a per-rule read never sees it.

The aggregation across the whole fleet is exactly what the engine already does: one
transitive closure over the entire SG set (every SG a node, every UserIdGroupPair an
edge), not a per-SG verdict.

Stdlib only. No external dependencies. No credentials. Python 3.10+.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Re-export the proven engine's public surface unchanged.
from _reach_engine import (  # noqa: E402
    Finding,
    Reachability,
    build_graph,
    load_instances,
    load_security_groups,
    run_reach,
)

__all__ = ["run_deep", "Finding", "Reachability", "build_graph", "load_instances", "load_security_groups"]


def run_deep(fixture_dir: Path) -> Reachability:
    """Run the validated reachability engine over one fleet fixture and return the
    same Reachability result shape. This is the ground-truth oracle the screening
    harness anchors its LLM judge against.

    For this estate/fleet harness the "aggregation across sub-items" is the single
    transitive closure the engine already computes over the WHOLE security-group set:
    every SG in the fleet is a node, every UserIdGroupPair an edge, and the result is
    one fleet-wide reachability verdict (the long needle path + blast radius, or
    clean), not a per-SG list. We do not re-implement that; we delegate to the proven
    engine unchanged.
    """
    return run_reach(Path(fixture_dir))

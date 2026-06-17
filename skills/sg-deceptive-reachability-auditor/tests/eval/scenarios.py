"""
Per-fixture contexts and expected answers for the sg-deceptive-reachability-auditor
screening eval.

The "expected_*" fields are the deterministic answers from the reused engine (_deep.py,
which delegates to the validated _reach_engine.py) run against each high-volume fleet
fixture. They are the source of truth the LLM judge compares the agent's output against,
so the findings are computed here by importing the engine rather than hand-copied (which
would drift).

Every fixture here is from the model's empirically-located WEAK region: LONG (4-6 hop)
lateral chains buried in a 10-13 SG fleet, plus DECEPTIVE / segmented-clean fleets where a
loud public exposure or a visible-but-orphaned deep SG-ref chain must NOT be reported as a
reachable path. There are NO short, obvious 2-3 hop direct paths -- those the base model
already aces, so they would lift the aggregate above the screening threshold and defeat the
purpose. The skill's value region IS the hard cases: four deceptive-clean fleets where the
cold agent tends to FABRICATE a critical path, and three buried-deep needles where it tends
to flag the loud surface and stop.

load_fixture_text renders the FULL volume the agent sees: every security group, every
instance, and the named entry + crown jewel -- a 10-13 SG haystack per fixture. The
control prompt (in run_eval.py) is deliberately GENERIC and does NOT name lateral movement,
chains, or reachability; these expected fields exist only for the judge, never for the agent.

Stdlib only. No external dependencies. `python scenarios.py` prints ground truth, no key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = TESTS_DIR.parent / "fixtures"

sys.path.insert(0, str(TESTS_DIR))
from _deep import run_deep  # noqa: E402

# Each entry pairs a fixture with the human-readable context the eval feeds the agent
# (generic -- a fleet description, no vector hint), plus the headline / fix / boundary the
# deterministic engine grounds (the judge's anchor only). Keep aligned with replay_*.py.
SCENARIOS = [
    {
        "id": "01-orphaned-front-internal-cidr",
        "context": "An 11-security-group production fleet. Entry is the internet; the crown jewel is the database tier.",
        "expected_headline": "CLEAN. The config SHOWS a deep SG-reference chain web -> app -> session cache -> db, which looks like a buried lateral path, but the web frontend accepts only the internal service-mesh CIDR (10.50.0.0/16), NOT the public ALB SG, so that chain is ORPHANED from the internet entry. The internet reaches only the directly-exposed public ALB and stops. The database is NOT reachable. Do not mistake the visible-but-disconnected chain for a reachable path, and do not over-flag the busy but correctly-scoped ruleset.",
        "expected_top_fix": "None. Do not invent a lateral path from the orphaned deep chain. The segmentation is correct. Still report the boundary (route tables, NACLs, live membership) the SG graph cannot confirm.",
        "expected_boundary_join": "the SG graph alone cannot confirm even the bounded reach is live (route tables, NACLs, instance membership); a deep chain that is disconnected on paper is still only on paper.",
    },
    {
        "id": "02-public-alb-no-sg-ref",
        "context": "An 11-security-group production fleet. A public ALB carries the only 0.0.0.0/0 (and ::/0) ingress on 443/80. Entry is the internet; the crown jewel is the database tier.",
        "expected_headline": "CLEAN. The loud 0.0.0.0/0 on the public ALB is the INTENDED public entry (that is what a public load balancer is for). A deep service chain web -> app -> internal services -> db is wired downstream, but NOTHING references the public ALB SG (it forwards to its target group by registered IP), so no SG-to-SG edge composes from the internet into the fleet. The database is NOT reachable. Do not headline the intended public ALB as a lateral chain and do not over-flag the busy but correctly-scoped ruleset.",
        "expected_top_fix": "None. The fleet is segmented and the public ALB exposure is intended. Do not invent a lateral path from the orphaned downstream chain. Still report the boundary (route tables, NACLs, live membership) the SG graph cannot confirm.",
        "expected_boundary_join": "the SG graph alone cannot confirm the bounded reach is live (route tables, NACLs, instance membership); the public ALB is a path to nothing further without an SG reference.",
    },
    {
        "id": "03-disjoint-public-vpn-islands",
        "context": "An 11-security-group production fleet across two AZs. Entry is the internet; the crown jewel is the database tier.",
        "expected_headline": "CLEAN. The fleet is two disconnected islands. The internet-facing island (public ALB -> web -> web-app) is wired by CIDR, not SG refs, and dead-ends. The data island carries a juicy-looking deep SG-ref chain admin plane -> data processor -> db (+ analytics cache), but the admin plane accepts only the corp VPN CIDR and has no inbound SG reference, so the data island is reachable only from the VPN, never from the internet. No edge joins the islands. The crown-jewel database is NOT reachable from the internet. Do not splice the two islands into a manufactured internet -> db route.",
        "expected_top_fix": "None. The two islands are correctly disconnected and the data island is VPN-only. Do not invent a cross-island lateral path. Still report the boundary (route tables, NACLs, live membership) the SG graph cannot confirm.",
        "expected_boundary_join": "the SG graph alone cannot confirm the bounded reach is live (route tables, NACLs, instance membership); the data island's deep chain is reach-on-paper and is not joined to any internet entry.",
    },
    {
        "id": "04-broken-segment-midchain",
        "context": "A 10-security-group production fleet. A public edge proxy carries the only 0.0.0.0/0 (and ::/0) ingress on 443. Entry is the internet; the crown jewel is the database tier.",
        "expected_headline": "CLEAN. A long service chain is VISIBLE (public edge proxy -> web -> app -> session cache -> db) and the edge proxy is the intended public entry, but the chain is CUT at the first internal hop: the web frontend accepts only the internal mesh CIDR (10.70.0.0/16), NOT the edge proxy SG, so the edge -> web link is not an SG edge and the rest of the chain is orphaned. The internet reaches only the directly-exposed edge proxy and stops. The database is NOT reachable. Do not mistake the visible-but-broken chain for a reachable path, and do not over-flag the busy but correctly-scoped ruleset.",
        "expected_top_fix": "None. The chain is broken at the edge -> web hop and the public edge exposure is intended. Do not invent a lateral path across the cut. Still report the boundary (route tables, NACLs, live membership) the SG graph cannot confirm.",
        "expected_boundary_join": "the SG graph alone cannot confirm the bounded reach is live (route tables, NACLs, instance membership); the orphaned tail of the chain is reach-on-paper and is not joined to the public edge proxy.",
    },
    {
        "id": "05-six-hop-cdn-waf-gw-app-svc-db",
        "context": "A 13-security-group production fleet. Entry is the internet; the crown jewel is the database tier.",
        "expected_headline": "Buried in the 13-SG fleet, the SG-to-SG edges compose into a SIX-hop reachable path internet -> cdn -> waf -> gw -> app -> svc -> db to the crown-jewel database -- the deepest chain in the set, with the billing-service settlement-writer as the final link. Each rule accepts exactly one upstream tier and is textbook in isolation; the depth is the point. The scoped tiers (bastion, monitoring, ci, ssm) and app-fed leaves (cache, queue, logs) are not the finding.",
        "expected_top_fix": "Confirm each of the six hops is an intended trust relationship; the database should not be transitively reachable from the public CDN origin. Break the chain at the hop that crosses a trust boundary (e.g. the svc->db settlement writer or gw->app).",
        "expected_boundary_join": "live membership of each SG on the six-hop chain, plus route tables / NACLs / app-auth along the path; a long chain is reach-on-paper.",
    },
    {
        "id": "06-compromised-ci-runner-deep",
        "context": "A 12-security-group production fleet. The entry point is a COMPROMISED CI runner host (instance i-06ci0001), not the internet. The crown jewel is the database tier.",
        "expected_headline": "From the compromised CI runner, the SG-to-SG edges compose into a FIVE-hop internal build-pipeline path ci -> build -> artifact -> deploy -> app -> db to the crown-jewel database. The separate public ALB -> web -> web-cache front door does not touch the data plane, so the only path to the crown jewel is this internal pipeline chain. The depth + the non-internet entry are the point; a per-rule read clears each pipeline rule in isolation and misses the composed path.",
        "expected_top_fix": "Confirm each hop from the CI runner is intended; the database should not be transitively reachable from a compromised build host five hops away. Break the chain at the hop that crosses a trust boundary (e.g. deploy->app or app->db).",
        "expected_boundary_join": "live membership of each SG on the chain, plus route tables / NACLs / app-auth along the path; reachability from a foothold is reach-on-paper until confirmed.",
    },
    {
        "id": "07-five-hop-ingress-mesh-broker-db",
        "context": "A 12-security-group production fleet. Entry is the internet; the crown jewel is the database tier.",
        "expected_headline": "Buried in the 12-SG fleet, the SG-to-SG edges compose into a FIVE-hop reachable path internet -> ingress -> mesh -> app -> broker -> db to the crown-jewel database, with the event-broker journal-writer as the offbeat final link. Each tier accepts exactly one upstream and is fine in isolation; the chain only appears when all five hops are composed. The service-fed leaves (cache, queue, logs) and scoped tiers (bastion, monitoring, ci, ssm) are not the finding.",
        "expected_top_fix": "Break the chain at the hop that should not exist; the database should not be transitively reachable from the public ingress controller five hops away. Confirm each SG-reference edge along the path is an intended trust relationship.",
        "expected_boundary_join": "which instances are live members of each referenced SG along the five hops, plus route tables / NACLs / app-auth -- reachability-on-paper is not exploitability.",
    },
]


def fixture_dir(scenario: dict) -> Path:
    return FIXTURES_DIR / scenario["id"]


def load_fixture_text(scenario: dict) -> str:
    """The raw security-group + instance JSON the agent is given for this scenario.

    Renders the FULL volume: every SG and every instance in the fleet, so the agent
    genuinely sees the 10-13 SG haystack (not a pre-filtered slice). The named entry
    point and crown-jewel tier come from meta.json. NOTE: the agent prompt itself
    (run_eval.py) is generic and does not mention lateral movement / chains / reachability.
    """
    d = fixture_dir(scenario)
    sgs = json.loads((d / "security-groups.json").read_text())
    parts = ["aws ec2 describe-security-groups output:", json.dumps(sgs, indent=2)]
    inst_path = d / "instances.json"
    if inst_path.exists():
        instances = json.loads(inst_path.read_text())
        parts += ["", "aws ec2 describe-instances output (instance -> SG membership):", json.dumps(instances, indent=2)]
    meta_path = d / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        entry = meta.get("entry", "internet")
        crown = meta.get("crown_jewel", "(unspecified)")
        parts += ["", f"Entry point: {entry}", f"Crown-jewel tier: {crown}"]
    return "\n".join(parts)


def expected_deep(scenario: dict) -> dict:
    """Run the reused deterministic engine to get the ground-truth findings for the judge.

    The engine computes ONE fleet-wide transitive closure over the whole SG set (the
    aggregation across all sub-items), yielding the long needle path + blast radius, or clean.
    """
    r = run_deep(fixture_dir(scenario))
    return {
        "codes": sorted(r.codes()),
        "top_severity": r.top_severity,
        "clean": r.clean,
        "shortest_path": r.shortest_path,
        "blast_radius": r.reachable,
        "edge_count": len(r.edges),
        "boundary_count": len(r.boundary),
        "sg_count": r.sg_count,
    }


# Alias kept for parity with the sibling harnesses' expected_reach() / expected_needle() naming.
expected_reach = expected_deep
expected_needle = expected_deep


if __name__ == "__main__":
    # `python tests/eval/scenarios.py` prints the ground-truth answers, no API key needed.
    for s in SCENARIOS:
        exp = expected_deep(s)
        path = " -> ".join(exp["shortest_path"]) if exp["shortest_path"] else "(no path)"
        hops = len(exp["shortest_path"]) - 1 if exp["shortest_path"] else 0
        print(f"{s['id']:<34} codes={str(exp['codes']):<20} top={str(exp['top_severity']):<8} "
              f"clean={exp['clean']!s:<5} sgs={exp['sg_count']} edges={exp['edge_count']}")
        print(f"{'':<34} path={path}  ({hops} hops)")
        print(f"{'':<34} blast_radius={exp['blast_radius']}")

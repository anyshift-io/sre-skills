"""
Reference implementation of the lateral-movement-reachability-auditor methodology.

This module is a deterministic stand-in for what an AI agent does when it follows
SKILL.md. It exists so replay tests can assert that the methodology, applied to a
known set of security groups, produces the expected reachability findings -- and so
the control-only screening eval has a ground truth to anchor its LLM judge against.

The job is a GRAPH problem, and the whole point of the skill is the composition the
graph makes visible. The input is a set of security groups whose ingress rules
reference OTHER security groups (UserIdGroupPairs) plus an instance->SG membership
map. A per-rule read sees "app accepts from web" and "db accepts from app" as two
individually fine rules and misses that internet -> web -> app -> db is one reachable
path. This module composes those SG-to-SG edges into multi-hop paths.

Model
-----
Build a DIRECTED graph over security groups. An edge A -> B exists if SG B has an
INGRESS rule whose UserIdGroupPairs includes SG A (B accepts traffic FROM A), meaning
a host in A can reach a host in B. The synthetic node "internet" has an edge
internet -> X for every SG X with a 0.0.0.0/0 (or ::/0) ingress rule.

From the entry point named in meta.json ("internet" or a compromised instance id,
which resolves to that instance's SGs), compute the transitive closure with BFS
(visited set -> cycles terminate). Findings:

  P1 (critical) -- a path entry -> ... -> crown-jewel tier exists; report the SHORTEST
     path as an explicit ordered hop list.
  B1 (high)     -- the full reachable set (blast radius) from the entry, when it spans
     more than the entry tier itself.
  H1 (high)     -- a "pivot/hub" SG that bridges two otherwise-isolated reachable
     regions: removing it disconnects part of the blast radius (an articulation point
     in the reachable subgraph).

A SEGMENTED graph where no path reaches the crown jewel is CLEAN: the audit reports
the blast radius is bounded and does NOT include the crown jewel (and still reports
the boundary it cannot cross).

Stdlib only. No external dependencies. No external credentials. Python 3.10+.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

INTERNET = "internet"


@dataclass
class Finding:
    """One reachability finding, derived from the SG graph + membership alone."""

    code: str           # P1 (path to crown jewel) | B1 (blast radius) | H1 (hub/pivot)
    severity: str       # critical | high | medium | low
    attribute: str      # the SG(s) / edge / path the finding is grounded in
    title: str
    detail: str
    recommendation: str
    # For path-based findings, the ordered hop list (e.g. ["internet","web","app","db"]).
    path: list[str] = field(default_factory=list)


@dataclass
class Reachability:
    """Structured output of the methodology, one per audited graph."""

    entry: str                                  # the entry-point label (resolved)
    crown_jewel: str | None                     # the crown-jewel tier label, if named
    sg_count: int = 0
    findings: list[Finding] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)   # directed A->B (reach)
    reachable: list[str] = field(default_factory=list)           # blast radius (labels), entry excluded
    shortest_path: list[str] = field(default_factory=list)       # entry..crown jewel, if any
    boundary: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return len(self.findings) == 0

    @property
    def top_severity(self) -> str | None:
        if not self.findings:
            return None
        return min(self.findings, key=lambda f: _SEVERITY_RANK[f.severity]).severity

    def codes(self) -> set[str]:
        return {f.code for f in self.findings}


# --- Loading ------------------------------------------------------------------------


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def load_security_groups(path: Path) -> list[dict]:
    with path.open() as f:
        doc = json.load(f)
    if isinstance(doc, dict) and "SecurityGroups" in doc:
        return list(doc["SecurityGroups"])
    if isinstance(doc, list):
        return doc
    return [doc]


def load_instances(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        doc = json.load(f)
    if isinstance(doc, dict) and "Reservations" in doc:
        out: list[dict] = []
        for r in doc["Reservations"]:
            out.extend(r.get("Instances", []))
        return out
    if isinstance(doc, dict) and "Instances" in doc:
        return list(doc["Instances"])
    if isinstance(doc, list):
        return doc
    return [doc]


# --- Label helpers ------------------------------------------------------------------


def _sg_label(sg: dict) -> str:
    """A human label for an SG, preferring a `tier` tag, then GroupName, then GroupId."""
    for tag in _as_list(sg.get("Tags")):
        if isinstance(tag, dict) and tag.get("Key") in ("tier", "Name"):
            if tag.get("Value"):
                return str(tag["Value"])
    return sg.get("GroupName") or sg.get("GroupId") or "<unknown>"


def _rule_is_internet_facing(rule: dict) -> bool:
    for r in _as_list(rule.get("IpRanges")):
        if isinstance(r, dict) and r.get("CidrIp") == "0.0.0.0/0":
            return True
    for r in _as_list(rule.get("Ipv6Ranges")):
        if isinstance(r, dict) and r.get("CidrIpv6") == "::/0":
            return True
    return False


# --- Graph construction -------------------------------------------------------------


def build_graph(sgs: list[dict]) -> tuple[dict[str, set[str]], set[str]]:
    """Build the directed reachability graph keyed by GroupId.

    Returns (adjacency, internet_facing) where adjacency[A] is the set of GroupIds a
    host in A can reach in one hop, and internet_facing is the set of GroupIds with a
    0.0.0.0/0 (or ::/0) ingress rule. An edge A -> B is created when SG B has an INGRESS
    rule whose UserIdGroupPairs names A (B accepts FROM A).
    """
    ids = {sg.get("GroupId") for sg in sgs if sg.get("GroupId")}
    adjacency: dict[str, set[str]] = {gid: set() for gid in ids}
    internet_facing: set[str] = set()

    for sg in sgs:
        b = sg.get("GroupId")
        if not b:
            continue
        for rule in _as_list(sg.get("IpPermissions")):
            if _rule_is_internet_facing(rule):
                internet_facing.add(b)
            for pair in _as_list(rule.get("UserIdGroupPairs")):
                a = pair.get("GroupId") if isinstance(pair, dict) else None
                if a and a in ids:
                    adjacency.setdefault(a, set()).add(b)  # A can reach B

    if internet_facing:
        adjacency[INTERNET] = set(internet_facing)
    return adjacency, internet_facing


def _bfs_closure(adjacency: dict[str, set[str]], start: set[str]) -> dict[str, int]:
    """BFS from a set of start nodes. Returns {node: hop-distance}. Cycles terminate
    because a node is enqueued at most once (visited == keys of the dist map)."""
    dist: dict[str, int] = {s: 0 for s in start}
    queue: deque[str] = deque(start)
    while queue:
        node = queue.popleft()
        for nxt in adjacency.get(node, set()):
            if nxt not in dist:
                dist[nxt] = dist[node] + 1
                queue.append(nxt)
    return dist


def _shortest_path(adjacency: dict[str, set[str]], start: set[str], target: str) -> list[str]:
    """Shortest path (BFS, so fewest hops) from any start node to target, or []."""
    if target in start:
        return [target]
    prev: dict[str, str] = {}
    seen: set[str] = set(start)
    queue: deque[str] = deque(start)
    while queue:
        node = queue.popleft()
        for nxt in adjacency.get(node, set()):
            if nxt in seen:
                continue
            seen.add(nxt)
            prev[nxt] = node
            if nxt == target:
                path = [nxt]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                path.reverse()
                # Prepend the start node the path emerged from (already the head).
                return path
            queue.append(nxt)
    return []


def _undirected_components(nodes: set[str], adjacency: dict[str, set[str]]) -> int:
    """Number of connected components among `nodes`, treating edges as undirected and
    only counting edges whose BOTH endpoints are in `nodes`. Used to decide whether the
    set a candidate gates is one region (a linear continuation) or several (a fan-out)."""
    if not nodes:
        return 0
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for a, succ in adjacency.items():
        if a not in nodes:
            continue
        for b in succ:
            if b in nodes:
                adj[a].add(b)
                adj[b].add(a)
    seen: set[str] = set()
    comps = 0
    for n in nodes:
        if n in seen:
            continue
        comps += 1
        stack = [n]
        seen.add(n)
        while stack:
            x = stack.pop()
            for y in adj[x]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
    return comps


def _articulation_hubs(
    adjacency: dict[str, set[str]], start: set[str], reachable: set[str]
) -> list[str]:
    """SGs that, if removed, disconnect TWO OR MORE otherwise-isolated reachable regions
    -- a true pivot/hub, not just any node on a linear chain.

    For each candidate node (reachable, not a start node), recompute the closure with the
    node deleted and find the set it gated (`lost`). A node is a hub only when `lost`
    forms two or more mutually-isolated regions (a fan-out bridge), distinguishing a
    shared-services SG that joins separate tiers from an ordinary intermediate hop on a
    single linear path (which gates only its own downstream continuation -- one region).

    Returns hubs ordered by how much they bridge (most regions, then most nodes, gated).
    """
    base = reachable - set(start)
    scored: list[tuple[int, int, str]] = []
    for cand in sorted(base):
        pruned: dict[str, set[str]] = {
            n: {m for m in succ if m != cand}
            for n, succ in adjacency.items()
            if n != cand
        }
        still = set(_bfs_closure(pruned, start)) - set(start)
        lost = base - still - {cand}
        if not lost:
            continue
        regions = _undirected_components(lost, adjacency)
        if regions >= 2:  # a fan-out bridge, not a linear continuation
            scored.append((regions, len(lost), cand))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return [c for _, _, c in scored]


# --- Boundary -----------------------------------------------------------------------


def _boundary_notes(entry_is_internet: bool, has_crown: bool) -> list[str]:
    notes = [
        "Reachability-on-paper is not exploitability. An edge means an SG accepts the "
        "referenced SG; it does not mean a live host is listening, nor that the route "
        "actually carries traffic. Join: SG graph to the live ENIs/instances actually "
        "in each SG.",
        "Subnet route tables decide whether two SGs are even on a routable path. An SG "
        "edge across unrouted subnets reaches nothing. Join: SG graph to the route tables.",
        "Network ACLs are a stateless layer below security groups and can deny traffic "
        "the SG graph would allow. Join: SG graph to the subnet NACLs.",
        "Application-layer authentication (a database password, an mTLS handshake, an "
        "app token) can stop a network-reachable hop from becoming access. Join: "
        "network reachability to the app-layer auth on each tier.",
    ]
    if entry_is_internet:
        notes.append(
            "The internet edge assumes the 0.0.0.0/0 SG is on a host with a public IP and "
            "an internet route. Without that, the entry point itself is unreachable. Join: "
            "internet-facing SG to its host's public IP + route table."
        )
    if has_crown:
        notes.append(
            "Whether the crown-jewel tier currently has a running host is a membership "
            "question the SG graph cannot answer; an empty SG is a path to nothing. Join: "
            "crown-jewel SG to its current instance membership."
        )
    return notes


# --- Orchestration ------------------------------------------------------------------


def run_reach(fixture_dir: Path) -> Reachability:
    """End-to-end: load the SG graph + instances, resolve the entry point and crown
    jewel from meta.json, compute the transitive closure, and return the Reachability.

    meta.json shape:
      {"entry": "internet" | "<instance-id>", "crown_jewel": "<tier-name-or-GroupId>"}
    The crown jewel is matched against SG tier/Name tags, GroupName, or GroupId.
    """
    sgs = load_security_groups(fixture_dir / "security-groups.json")
    instances = load_instances(fixture_dir / "instances.json")

    meta: dict = {}
    meta_path = fixture_dir / "meta.json"
    if meta_path.exists():
        with meta_path.open() as f:
            meta = json.load(f)
    entry_spec = meta.get("entry", "internet")
    crown_spec = meta.get("crown_jewel")

    adjacency, internet_facing = build_graph(sgs)

    id_to_label = {sg["GroupId"]: _sg_label(sg) for sg in sgs if sg.get("GroupId")}
    id_to_label[INTERNET] = "internet"

    def label(gid: str) -> str:
        return id_to_label.get(gid, gid)

    # Resolve the crown-jewel SG id from its spec (tier tag / GroupName / GroupId).
    crown_id: str | None = None
    if crown_spec:
        for sg in sgs:
            gid = sg.get("GroupId")
            if gid == crown_spec or _sg_label(sg) == crown_spec or sg.get("GroupName") == crown_spec:
                crown_id = gid
                break

    # Resolve the entry point to a set of start GroupIds.
    entry_is_internet = entry_spec == INTERNET
    if entry_is_internet:
        start_ids: set[str] = {INTERNET}
        entry_label = "internet"
    else:
        start_ids = set()
        entry_label = entry_spec
        for inst in instances:
            if inst.get("InstanceId") == entry_spec:
                for s in _as_list(inst.get("SecurityGroups")):
                    gid = s.get("GroupId") if isinstance(s, dict) else None
                    if gid:
                        start_ids.add(gid)
                for tag in _as_list(inst.get("Tags")):
                    if isinstance(tag, dict) and tag.get("Key") == "Name" and tag.get("Value"):
                        entry_label = tag["Value"]
        if not start_ids:
            # Fall back to treating the spec as an SG label/id directly.
            for sg in sgs:
                if _sg_label(sg) == entry_spec or sg.get("GroupId") == entry_spec:
                    start_ids.add(sg["GroupId"])

    dist = _bfs_closure(adjacency, start_ids)
    reachable_ids = set(dist) - set(start_ids)
    if INTERNET in reachable_ids:
        reachable_ids.discard(INTERNET)

    # Directed reach edges, excluding the synthetic internet node from the count surface
    # but keeping internet->X edges visible in the edge list.
    edges: list[tuple[str, str]] = []
    for a, succ in adjacency.items():
        for b in succ:
            edges.append((label(a), label(b)))
    edges.sort()

    shortest = _shortest_path(adjacency, start_ids, crown_id) if crown_id else []
    shortest_labels = [label(n) for n in shortest]

    # Lateral reach is the set of tiers reached by composing at least one SG-to-SG hop
    # BEYOND the entry-adjacent tier (distance >= 2 from the entry). A tier that is only
    # directly internet-facing (distance 1, the expected public exposure) is not lateral
    # movement; it is a different auditor's finding. The blast-radius finding fires only
    # when the closure genuinely composes edges into multi-hop reach -- so a segmented
    # graph where the chain is broken after the first hop stays clean here.
    lateral_ids = {g for g in reachable_ids if dist.get(g, 0) >= 2}

    findings: list[Finding] = []

    # P1 -- a path from the entry to the crown jewel.
    if crown_id and shortest:
        hops = len(shortest) - 1
        findings.append(Finding(
            code="P1", severity="critical",
            attribute=" -> ".join(shortest_labels),
            title=f"Reachable path from {entry_label} to the crown-jewel tier ({hops} hops)",
            detail=(
                f"Composing the SG-to-SG edges yields a {hops}-hop path from {entry_label} to "
                f"the crown-jewel tier: {' -> '.join(shortest_labels)}. No single ingress rule "
                "is alarming -- each tier accepting the tier in front of it is routine -- but the "
                "edges compose into one reachable path that a per-rule read never assembles. This "
                "is the lateral-movement chain the audit exists to surface."
            ),
            recommendation=(
                "Break the chain at the hop that should not exist: a low-trust tier should not be "
                "able to reach the crown jewel even transitively. Re-scope the offending ingress "
                "(remove the SG reference, or interpose a broker/bastion tier), and confirm each "
                "edge on the path is an intended trust relationship."
            ),
            path=shortest_labels,
        ))

    # B1 -- the blast radius, when the closure composes at least one lateral hop
    # (distance >= 2) beyond the directly-exposed entry-adjacent tier.
    if lateral_ids:
        radius_labels = sorted(label(g) for g in reachable_ids)
        crown_in = crown_id in reachable_ids if crown_id else False
        findings.append(Finding(
            code="B1", severity="high",
            attribute=f"{len(radius_labels)} SG(s) reachable from {entry_label}",
            title=f"Blast radius from {entry_label}: {len(radius_labels)} reachable tier(s)",
            detail=(
                f"From {entry_label}, the transitive closure of the SG graph reaches "
                f"{len(radius_labels)} other tier(s): {', '.join(radius_labels)}. "
                + ("The crown-jewel tier is inside this radius. " if crown_in else
                   "The crown-jewel tier is NOT inside this radius. ")
                + "This is the set of tiers a foothold at the entry can pivot to without any "
                "further misconfiguration -- it is bounded by the edges, not by any single rule."
            ),
            recommendation=(
                "Confirm every tier in the blast radius is intended to be reachable from the "
                "entry. Each unintended tier in the set is an edge to re-scope; minimize the "
                "transitive reach, not just the direct rules."
            ),
        ))

    # H1 -- a hub/pivot SG bridging two otherwise-isolated reachable regions.
    hubs = _articulation_hubs(adjacency, start_ids, reachable_ids | set(start_ids))
    # A hub is an INTERMEDIATE bridge, not the entry node nor the directly-exposed
    # front-door tier (distance 1, which is the expected public ingress, a different
    # auditor's finding). Restrict to nodes at least two hops in -- the quiet shared SG
    # that joins regions, not the obvious internet-facing edge.
    hubs = [h for h in hubs if h not in start_ids and h != INTERNET and dist.get(h, 0) >= 2]
    if hubs:
        hub = hubs[0]
        findings.append(Finding(
            code="H1", severity="high",
            attribute=f"hub SG {label(hub)}",
            title=f"Pivot/hub SG bridges otherwise-isolated regions ({label(hub)})",
            detail=(
                f"The SG '{label(hub)}' is a pivot: it is the only reachable bridge between two "
                "regions of the graph that are otherwise isolated from the entry. Remove it and "
                "part of the blast radius disconnects. A shared-services SG (monitoring, CI, a "
                "jump tier) that everything references is exactly this shape -- it quietly joins "
                "tiers that were never meant to reach each other."
            ),
            recommendation=(
                f"Treat '{label(hub)}' as a high-value chokepoint: minimize what references it and "
                "what it can reach, since compromising it (or a host in it) unlocks both regions it "
                "bridges. Split a shared-services SG per consumer rather than one SG every tier trusts."
            ),
        ))

    findings.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.code))

    return Reachability(
        entry=entry_label,
        crown_jewel=(label(crown_id) if crown_id else crown_spec),
        sg_count=len(sgs),
        findings=findings,
        edges=edges,
        reachable=sorted(label(g) for g in reachable_ids),
        shortest_path=shortest_labels,
        boundary=_boundary_notes(entry_is_internet=entry_is_internet, has_crown=crown_id is not None),
    )

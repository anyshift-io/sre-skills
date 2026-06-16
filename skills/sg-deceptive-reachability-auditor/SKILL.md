---
name: sg-deceptive-reachability-auditor
description: Audit a fleet of AWS security groups for the multi-hop lateral-movement path that no single ingress rule reveals. Builds a directed reachability graph from the SG-to-SG references (an ingress rule on SG B naming SG A means a host in A can reach B), adds an internet edge for every 0.0.0.0/0 rule, then composes those edges into the transitive closure from a named entry point (the internet, or a compromised host). Reports the shortest reachable path to the crown-jewel tier, the blast radius, and any pivot/hub SG that bridges otherwise-isolated regions, each ranked by severity with a fix. Its discipline is symmetric: on a segmented or orphaned fleet where the chain does NOT reach the crown jewel, it reports clean and names the boundary instead of fabricating a path. Then it states what the SG graph alone cannot answer (live host membership, route tables, NACLs, app-layer auth). Use when asked to review a security-group fleet for lateral movement, blast radius, or whether the internet can reach a sensitive tier. Vendor-neutral; runs offline against describe-security-groups + describe-instances JSON with no Anyshift account.
---

# sg-deceptive-reachability-auditor

Reachability-audit skill for a fleet of AWS security groups. Takes the
`describe-security-groups` output for the fleet (plus `describe-instances` for the
instance-to-SG membership), composes the SG-to-SG references into a directed graph,
and answers one question a per-rule read cannot: from a named entry point, what can
actually be reached, and does any path reach the crown-jewel tier. It returns the
shortest path, the blast radius, and any pivot hub, ranked by severity, then names
exactly where the SG graph stops being able to answer the question.

The job is a graph problem, and the whole point of the skill is the composition the
graph makes visible. A per-rule read sees "app accepts from web" and "db accepts from
app" as two individually fine rules and never assembles that `internet -> web -> app
-> db` is one reachable path. In a fleet of 10-13 security groups, that chain is buried
among scoped tiers (bastion, monitoring, ci, ssm) and app-fed leaves (cache, queue,
logs), and the loud `0.0.0.0/0` rule on the front door draws the eye away from it. This
skill composes the edges instead of clearing each rule in isolation.

## When to invoke

- An agent is asked to review a security-group fleet for lateral movement, blast
  radius, or "can the internet reach the database."
- A fleet is being shipped or changed and the question is whether a low-trust tier can
  reach a sensitive one transitively, not just directly.
- An incident assumes a host is compromised and the question is what that foothold can
  pivot to.
- A fleet *looks* segmented and the claim "the database is isolated" needs to be
  confirmed against the actual edges rather than taken on trust.

## What this skill reads, and what it does not

It reads the static configuration of a **fleet of security groups** plus the
**instance-to-SG membership**. Both are EC2 control-plane reads
(`describe-security-groups`, `describe-instances`). That is the entire input. The audit
is correct and complete *for what the SG graph can tell you*, and it is explicit about
the rest. Reachability-on-paper is not exploitability, and every audit ends by naming
the joins it cannot make:

- It does **not** confirm a live host is listening. An edge means an SG accepts the
  referenced SG; it does not mean an instance in that SG is running and serving. An
  empty SG is a path to nothing. Join: SG graph to the live ENIs/instances in each SG.
- It does **not** read route tables. Two SGs on unrouted subnets are not on a routable
  path no matter what the ingress rules allow. Join: SG graph to the subnet route tables.
- It does **not** read network ACLs. A NACL is a stateless layer below security groups
  and can deny traffic the SG graph would allow. Join: SG graph to the subnet NACLs.
- It does **not** read app-layer auth. A database password, an mTLS handshake, or an
  app token can stop a network-reachable hop from becoming access. Join: network
  reachability to the app-layer auth on each tier.

Every audit ends by naming these. A clean (segmented) fleet still gets a boundary
section, because a network-segmented fleet is not a proven-safe system.

## The model

Build a **directed graph over security groups**. An edge `A -> B` exists when SG B has
an **ingress** rule whose `UserIdGroupPairs` includes SG A (B accepts traffic *from* A),
meaning a host in A can reach a host in B. A synthetic node `internet` has an edge
`internet -> X` for every SG X with a `0.0.0.0/0` (or `::/0`) ingress rule.

From the entry point named for the audit (`internet`, or a compromised instance id that
resolves to that instance's SGs), compute the transitive closure with BFS. A visited set
makes cycles terminate. The findings fall out of the closure.

## The methodology, in order

### 1. Parse the fleet into edges

Before any judgment, turn the JSON into the graph:

- For each SG, read its `IpPermissions` (ingress). Every `UserIdGroupPairs` entry naming
  another SG in the fleet is an **incoming** edge: `referenced-SG -> this-SG`. This is
  the step a naive read skips. The SG-reference arrays are where the chain lives.
- Every `0.0.0.0/0` / `::/0` `IpRanges` / `Ipv6Ranges` entry makes the SG
  internet-facing: `internet -> this-SG`.
- Read `describe-instances` for the instance-to-SG membership, so the entry point (a
  compromised host) resolves to a set of start SGs, and so a tier with no running host
  can be flagged as a path to nothing at the boundary.
- Label each SG by its `tier` / `Name` tag, then `GroupName`, then `GroupId`, so the path
  reads as `internet -> web -> app -> db`, not as a list of `sg-` ids.

### 2. Compute the closure and the path (P1)

Run BFS from the entry's start set. The reachable set is the closure minus the start.
If the crown-jewel tier is in the closure, compute the **shortest path** (fewest hops)
to it and report it as the headline:

- **P1 (critical) — a reachable path from the entry to the crown jewel.** Report the
  shortest path as an explicit ordered hop list (`internet -> cdn -> waf -> gw -> app ->
  svc -> db`). No single ingress rule is alarming; each tier accepting the tier in front
  of it is routine. The edges compose into one path a per-rule read never assembles.
  This is the lateral-movement chain the audit exists to surface, and on a needle fleet
  it is *the* primary finding, named end to end, not a footnote under the loud public
  rule.

### 3. Report the blast radius (B1)

- **B1 (high) — the blast radius.** When the closure composes at least one lateral hop
  (distance >= 2 from the entry, i.e. beyond the directly-exposed front-door tier), report
  the full reachable set: the tiers a foothold at the entry can pivot to with no further
  misconfiguration. State explicitly whether the crown jewel is inside the radius. A
  fleet whose chain breaks after the first hop has no lateral reach and does not fire
  B1 — that distinction is load-bearing for the clean fleets.

### 4. Find the pivot hub (H1)

- **H1 (high) — a pivot/hub SG bridging otherwise-isolated regions.** For each
  intermediate reachable SG, recompute the closure with that node removed. If its removal
  disconnects **two or more** mutually-isolated regions of the blast radius, it is a true
  pivot (an articulation point), not just an ordinary hop on a linear chain. A
  shared-services SG (monitoring, CI, a jump tier) that every tier references is exactly
  this shape: it quietly joins tiers that were never meant to reach each other. Do not
  report the entry node or the directly-internet-facing front door as a hub; those are a
  different auditor's finding.

### 5. Stay quiet on the deceptive-clean fleet

This is the half of the skill that the naive read gets wrong in the other direction.
A segmented, orphaned, or broken fleet where **no path reaches the crown jewel is
CLEAN**, and the audit must say so instead of manufacturing a path. The same composition
discipline is what proves it. Specifically:

- An **orphaned** deep chain (the deep tiers reference each other, but the front tier
  accepts only an internal service-mesh CIDR, not the public SG) is not a reachable path.
  Do not report it as one.
- An intended **public ALB** taking `0.0.0.0/0` is the expected ingress, not the lateral
  path and not the headline.
- A **disjoint** data island (a public region and an unconnected private region) must not
  be spliced into a manufactured `internet -> db` route.
- A **broken** mid-chain segment (the chain is cut at one hop) is not reachable across
  the cut.
- Do not drown the real finding, or the clean verdict, in a wall of low-value nitpicks
  about correctly-scoped tiers (bastion, monitoring, ci, ssm).

On a clean fleet the audit reports: no reachable path to the crown jewel, the bounded
blast radius (and the boundary it cannot cross), and the join checks that would confirm
the segmentation holds. It does **not** invent a critical.

### 6. Rank and report, then name the boundary

Order findings by severity (critical, high). For each: the path/SG it is grounded in,
what it means, and the fix. Then list the boundary from step "What this skill reads."
A clean fleet still gets a boundary section.

## Severity model

| Severity | Meaning |
|---|---|
| **critical** | A composed path from the entry reaches the crown-jewel tier. P1. |
| **high** | A foothold at the entry can pivot laterally, or a single SG bridges isolated regions. B1, H1. |

There is no low band here: a reachability finding is grounded in the composed graph, not
in a heuristic. The uncertainty lives entirely in the boundary (is a host live, is the
subnet routed, does a NACL deny, is there app auth), which is why the boundary section is
mandatory rather than a footnote.

## Rule reference

| Code | Rule | Severity | Grounded in |
|---|---|---|---|
| P1 | Reachable path from the entry to the crown-jewel tier | critical | shortest path in the SG closure |
| B1 | Blast radius spans a lateral hop (distance >= 2) beyond the front door | high | transitive closure from the entry |
| H1 | Pivot/hub SG bridges two or more otherwise-isolated reachable regions | high | articulation point in the reachable subgraph |

The matching half of every rule is the clean verdict: P1 absent (no path), B1 absent
(no lateral hop), H1 absent (no bridge) on a segmented fleet is the correct, complete
output, not a failure to find something.

## Output format

The agent's final message in any invocation must include:

1. **Fleet**: SG count, the entry point, the crown-jewel tier.
2. **Findings**: ranked by severity, each with the code, the path/SG it is grounded in,
   what it means, and the fix. The P1 path named hop by hop. Or "no reachable path to the
   crown jewel" for a segmented fleet, with the bounded blast radius stated.
3. **Boundary**: the joins this audit could not make (live membership, route tables,
   NACLs, app-layer auth), stated explicitly so the gap is visible instead of silent.

## Worked examples

Seven end-to-end fixtures are committed under `fixtures/`, each a fleet of 10-13 security
groups with a runnable replay test. They are split between buried needles and
deceptive-clean fleets, with no short obvious 2-3 hop path in either set:

- [`05-six-hop-cdn-waf-gw-app-svc-db`](./fixtures/05-six-hop-cdn-waf-gw-app-svc-db/): a
  six-hop service chain (CDN to WAF to gateway to app to billing service to db) wired with
  ordinary single-upstream references; the P1 needle (critical).
- [`06-compromised-ci-runner-deep`](./fixtures/06-compromised-ci-runner-deep/): the entry
  is a compromised CI host, not the internet; the path composes from the foothold inward.
- [`07-five-hop-ingress-mesh-broker-db`](./fixtures/07-five-hop-ingress-mesh-broker-db/):
  a five-hop ingress-to-mesh-to-broker-to-db chain.
- [`01-orphaned-front-internal-cidr`](./fixtures/01-orphaned-front-internal-cidr/): the
  deep chain exists but the front tier accepts only the internal mesh CIDR, so it is
  orphaned from the internet entry. Clean.
- [`02-public-alb-no-sg-ref`](./fixtures/02-public-alb-no-sg-ref/): an intended public ALB
  on `0.0.0.0/0` with no onward SG reference. Clean (the public rule is not the headline).
- [`03-disjoint-public-vpn-islands`](./fixtures/03-disjoint-public-vpn-islands/): a public
  island and an unconnected private island; no route between them. Clean.
- [`04-broken-segment-midchain`](./fixtures/04-broken-segment-midchain/): a deep chain cut
  at one mid-chain hop, so it does not reach the crown jewel. Clean.

## Replay tests

Every fixture has a replay test in `tests/` that runs the methodology (via the
deterministic reference engine `tests/_reach_engine.py`, wrapped by `tests/_deep.py`)
against the committed JSON, with no external credentials. Run from the skill directory:

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

The seven tests cover the three needle paths (P1/B1/H1 present, hops correct) and the
four deceptive-clean fleets (no path fabricated). Tests exit non-zero if the audit
composes the wrong path or invents one on a clean fleet. See
[`tests/README.md`](./tests/README.md) for the fixture schema.

## Failure modes

This skill is wrong in predictable ways. Read [`FAILURE_MODES.md`](./FAILURE_MODES.md)
before relying on it. Highlights:

- It audits reachability, not exploitability. A path that passes every edge can reach a
  tier with no live host, an unrouted subnet, a denying NACL, or app-layer auth that stops
  the hop. Reachability-on-paper is a hypothesis to confirm, not a breach.
- The crown-jewel tier and the entry point are supplied by the caller. A wrong entry or a
  mislabelled crown jewel changes the path.
- It reasons over the SG references and the internet edge only. A reachable route via a
  peering connection, a transit gateway, or a VPC endpoint that does not appear as an SG
  reference is outside the graph this skill builds.

## Anyshift integration (opt-in)

The audit above runs end-to-end against the `describe-security-groups` +
`describe-instances` output the user already has. No Anyshift dependency.

Every boundary note in this skill is a join: SG graph to live instance membership, SG
graph to the route tables, SG graph to the subnet NACLs, network reachability to the
app-layer auth on each tier. The Anyshift MCP can act as a context primer by resolving
those joins from a versioned resource graph, so a P1 path can be confirmed (the host is
live, the subnet is routed, no NACL denies) instead of left as a hypothesis at the
boundary. A measured "with vs without" delta will be published here once the integration
has been exercised against the replay fixtures.

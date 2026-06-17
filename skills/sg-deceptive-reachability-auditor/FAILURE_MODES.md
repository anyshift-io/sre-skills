# Failure modes: sg-deceptive-reachability-auditor

This skill composes a reachability graph from security-group references. It is correct
for what that graph can express and wrong in the predictable ways below. Read this before
acting on a finding.

## 1. Reachability is not exploitability

A P1 path means every SG on the path accepts the SG in front of it. It does **not** mean
the path carries traffic. Each of these breaks a graph-reachable path without changing a
single ingress rule:

- **No live host.** An SG with no running instance is a path to nothing. The closure
  reaches the SG; the breach reaches an empty tier. Confirm membership before treating P1
  as live.
- **Unrouted subnets.** Two SGs whose subnets have no route to each other are not on a
  routable path. The SG edge is real; the route is absent.
- **A denying NACL.** Network ACLs are a stateless layer below security groups and can
  deny what the SG graph allows. The skill does not read them.
- **App-layer auth.** A database password, an mTLS handshake, or an app token can stop a
  network-reachable hop from becoming access.

The boundary section of every audit names these. A P1 path is a hypothesis to confirm
against the live estate, not a proven breach.

## 2. The entry point and crown jewel are caller-supplied

The path is computed *from* the named entry (`internet` or a compromised instance id)
*to* the named crown-jewel tier. A wrong entry, a mislabelled crown jewel, or a crown
jewel that resolves to no SG changes or empties the result. The skill resolves the crown
jewel by `tier`/`Name` tag, then `GroupName`, then `GroupId`; an untagged or misnamed
tier will not match.

## 3. Only SG references and the internet edge are in the graph

The graph has exactly two edge sources: SG-to-SG `UserIdGroupPairs` and `0.0.0.0/0` /
`::/0` ingress. A route that exists via a **VPC peering connection, a transit gateway, a
VPC endpoint, a load balancer target group, or a CIDR-based rule naming a specific
internal range** does not appear as an SG reference and is outside this graph. A fleet
that looks segmented to this skill may be connected by one of those.

## 4. The hub (H1) is structural, not behavioural

H1 fires when removing a node disconnects two or more isolated regions of the blast
radius. That is a property of the *graph*, not of how the SG is used. A shared-services
SG that is referenced widely but whose host runs nothing exploitable is still reported as
a hub. The finding says "this is the chokepoint if the path is live," which inherits the
caveat in section 1.

## 5. Clean is "no path in this graph," not "safe"

A clean verdict (no P1, no lateral B1, no H1) means the SG graph composes no path from the
entry to the crown jewel. It does **not** prove the fleet is safe: a peering edge
(section 3) may connect it, or the segmentation may rely on a NACL or route table this
skill cannot see and therefore cannot confirm. The clean verdict always ships with the
boundary, for exactly this reason. Do not read "clean" as "audited and proven isolated."

## 6. Direction matters, and it is easy to invert

The edge is `A -> B` when **B accepts A** (B's ingress names A). Reading the rule as "A
accepts B" inverts every edge and produces a mirror-image path that does not exist. The
reference engine encodes the direction once (`adjacency[A].add(B)` when B's ingress names
A); a hand audit that gets it backwards will fabricate paths and miss real ones.

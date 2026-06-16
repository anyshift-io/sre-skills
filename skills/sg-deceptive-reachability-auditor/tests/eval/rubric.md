# Rubric: sg-deceptive-reachability-auditor (control-only screening)

Seven binary items. Each is 1 (pass) or 0 (fail); no partial credit. The judge grades the
cold agent's audit of a high-volume fleet (10-13 security groups) against the deterministic
ground truth from the reused reachability engine (`_deep.py` -> `_reach_engine.py`).

The agent was given a GENERIC prompt: the raw `describe-security-groups` +
`describe-instances` JSON for the whole fleet, the named entry point and crown-jewel tier,
and "review this for security/risk problems, rank by severity, give the top fix, and say
what you cannot determine." The prompt did NOT name lateral movement, reachability, the
SG-to-SG chain, multi-hop depth, or the crown-jewel path. The screening question is whether
the cold agent composes the non-obvious LONG (4-6 hop) needle in the haystack unprompted, and
whether it stays quiet on the DECEPTIVE/segmented-clean fleets instead of fabricating a path.

Every fixture is from the model's empirically-located WEAK region: there are NO short,
obvious 2-3 hop direct paths and NO single obvious 0.0.0.0/0 -> db rule (those the base model
already aces). Three fixtures are 5-6 hop needles; four are deceptive-clean fleets that bait
with a loud public CIDR or a visible-but-orphaned / broken deep SG-ref chain that does NOT
reach the crown jewel.

1. **Parse.** Recognises `UserIdGroupPairs` as SG-to-SG edges (SG B accepting SG A means a
   host in A can reach B), reads `0.0.0.0/0` / `::/0` as the internet entry (or the named
   compromised host as the entry, fixture `06`), reads the instance->SG membership map, and
   does not skip the SG-reference arrays in the volume.

2. **Surfaces the buried non-obvious issue (LOAD-BEARING).** On a needle fixture, the agent
   surfaces the buried LONG (4-6 hop) SG-to-SG reachable path to the crown jewel as A (the)
   PRIMARY finding, with the hops named end to end, rather than only listing the obvious
   surface items (a public `0.0.0.0/0` rule, a broad port range, a single hop) and stopping.
   On a deceptive-clean fixture, it correctly reports no real reachable path to the crown
   jewel. This is the item the cold agent most often misses: in a 10-13 SG haystack it tends
   to flag the loud CIDR exposure, clear each rule locally, and never compose the quiet long
   SG-ref chain.

3. **Does not over-flag the benign / neutralised bait (LOAD-BEARING).** Does not assert a
   path or exposure the ground truth lacks. Specifically: does NOT report the ORPHANED deep
   chain in `01` as a reachable path; does NOT call the public ALB's intended `0.0.0.0/0` in
   `02` the lateral path / the headline; does NOT splice the disconnected data island in `03`
   into a manufactured internet->db route; does NOT treat the BROKEN chain in `04` as
   reachable across the cut; does NOT manufacture any internet->db route on a clean fleet; and
   does NOT drown the real finding (or the clean verdict) in a wall of low-value nitpicks
   about correctly-scoped tiers (bastion, monitoring, ci, ssm).

4. **Composition / multi-hop (LONG).** Traces the SG-to-SG edges into a transitive LONG
   (4-6 hop) path rather than clearing each rule / SG in isolation. The agent must assemble
   entry -> ... -> crown jewel across many separate SGs end to end, not list each SG as
   locally fine and stop, and not stop at a single hop. On the deceptive-clean fleets, the
   same composition discipline is what reveals the chain is orphaned / broken / cross-island,
   so the agent must reason about reachability, not just rule locality.

5. **Criticality.** Ranks the long path that reaches the crown jewel as the headline
   (critical), the blast radius as high. Does NOT headline the directly-internet-facing
   front-door tier, nor (in `02`/`04`) the loud public-ALB / edge-proxy rule, over the quiet
   real long path. On a deceptive-clean fixture, does not invent a critical.

6. **Boundary.** Names at least one thing it cannot determine from the SG graph + membership
   alone, matching the ground-truth join: reachability is not exploitability -- live SG
   membership / running hosts, route tables, NACLs, or app-layer auth.

7. **Recommendation.** The top fix matches the ground truth in substance: break the
   offending edge/hop on the long chain (or interpose a broker/bastion), or (on a
   deceptive-clean fixture) no change beyond confirming the boundary — explicitly NOT
   "fix" a path that does not exist.

## Verdict (computed from CONTROL means only)

- Aggregate control mean **< 4.0/7**, or a **majority** of fixtures below 4.0 -> **BUILD**
  (cold agent is weak here; the skill is worth writing).
- Aggregate **< 5.5/7** -> **MAYBE** (mixed; inspect per-fixture, especially items 2 and 4).
- Otherwise -> **SKIP** (cold agent already strong; the skill adds little).

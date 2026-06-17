# Tests: sg-deceptive-reachability-auditor

Deterministic ground-truth + replay tests for the deceptive-reachability screening fixtures.
No API key, no network, stdlib only.

## Engine (reused, not re-derived)

- `_reach_engine.py` — a **verbatim byte-for-byte copy** of the validated engine from the
  sibling skill `lateral-movement-reachability-auditor/tests/_reach.py` (carried in via the
  `sg-deep-lateral-auditor` screening harness). The graph build, BFS transitive closure,
  shortest-path, and articulation-hub logic are unchanged, so the ground truth here is
  provably the same computation.
- `_deep.py` — thin wrapper that re-exports the engine and exposes
  `run_deep(fixture_dir) -> Reachability`. It does NOT change engine logic. The
  `Reachability` result exposes `.findings` / `.codes()` / `.top_severity` / `.clean` /
  `.boundary` / `.shortest_path` / `.reachable`. For this fleet/estate harness, the
  "aggregation across sub-items" is the single fleet-wide transitive closure the engine
  already computes over the whole SG set (every SG a node, every UserIdGroupPair an edge).

## Scope: the model's WEAK region only

Every fixture is from the empirically-located weak region: LONG (4-6 hop) lateral chains
buried in a 10-13 SG haystack, plus DECEPTIVE / segmented-clean fleets where a loud public
exposure or a visible-but-orphaned deep SG-ref chain must NOT be reported as a reachable
path. There are **no short, obvious 2-3 hop direct paths** and **no fixture where the issue
is a single obvious public-to-db rule** — the base model trivially nails those (7.0), and
including them would lift the screening aggregate above threshold and defeat the purpose.

## Replay tests

One per fixture; each asserts the ground-truth verdict (long needle path / deceptive-clean):

```bash
for f in tests/replay_*.py; do python3 "$f"; done
```

| Fixture | Verdict | Needle / why clean |
|---|---|---|
| `01-orphaned-front-internal-cidr` | CLEAN | deep web->app->cache->db chain orphaned (web accepts the internal mesh CIDR, not the ALB SG) |
| `02-public-alb-no-sg-ref` | CLEAN | loud public ALB intended; nothing references the ALB SG (forwards by IP) |
| `03-disjoint-public-vpn-islands` | CLEAN | two disconnected islands; the data island's deep chain is VPN-only |
| `04-broken-segment-midchain` | CLEAN | visible edge->web->app->cache->db chain cut one hop in (web accepts the mesh CIDR, not the edge SG) |
| `05-six-hop-cdn-waf-gw-app-svc-db` | P1 + B1 + H1 | internet -> cdn -> waf -> gw -> app -> svc -> db (6 hops) |
| `06-compromised-ci-runner-deep` | P1 + B1 | ci -> build -> artifact -> deploy -> app -> db (5 hops, compromised-host entry) |
| `07-five-hop-ingress-mesh-broker-db` | P1 + B1 + H1 | internet -> ingress -> mesh -> app -> broker -> db (5 hops) |

Mix: 4 deceptive/segmented-clean, 3 buried-deep needles. Each fixture is a high-volume fleet
(10-13 SGs).

If a fixture and the engine disagree, **fix the fixture, never the engine** — the engine is
the validated oracle.

## Eval

`tests/eval/` holds the control-vs-treatment lift eval that measures the `SKILL.md`. See `tests/eval/README.md`.

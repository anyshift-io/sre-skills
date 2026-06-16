# Eval: sg-deceptive-reachability-auditor (control-only screening)

Decides whether the `sg-deceptive-reachability-auditor` skill is worth writing. There is
**no SKILL.md** and no treatment arm. We only run the CONTROL condition and read the verdict
off the control means.

## The experiment

The base model is strong on a directed question and on short SG paths. Earlier screening
showed it ACING short 2-3 hop SG paths (hub-pivot, flat mesh = 7.0) under a generic prompt,
but MISSING a 4-hop bastion chain (2.33, needle pass 0) and OVER-FLAGGING clean segmented
fleets (2.33). This harness is scoped ENTIRELY to that empirically-located weak region: the
**VOLUME + GENERIC-PROMPT + LONG-NEEDLE / DECEPTIVE-CLEAN** condition. A cold agent gets the
full `describe-security-groups` + `describe-instances` JSON for a 10-13 SG fleet and a
GENERIC "review this for problems" prompt that does **not** name lateral movement,
reachability, multi-hop chains, or the crown-jewel path. The question is whether it composes
the quiet LONG (4-6 hop) SG-reference needle out of the haystack unprompted — and, on the
deceptive-clean fleets, whether it correctly stays quiet instead of fabricating an
internet->db path that the segmentation actually neutralises.

This harness leans hard on the second failure mode. Four of the seven fixtures are
**deceptive-clean**: a deep chain that is orphaned because the front tier accepts an internal
CIDR rather than the public ALB SG (`01`), a loud public ALB that nothing SG-references
(`02`), two disjoint islands with the data island VPN-only (`03`), and a broken-segment fleet
where the chain is cut one hop in (`04`). On all four the engine returns CLEAN, and the cold
agent is expected to FABRICATE a critical path. The other three are **buried-deep needles**
(5-6 hops) with NO short/obvious public-to-db hop.

There are **no short, obvious 2-3 hop direct paths** here, and **no fixture where the issue
is a single obvious 0.0.0.0/0 -> db rule** — the base model already aces those, so they would
lift the aggregate above the screening threshold and defeat the purpose.

| Fixture | Verdict | Needle / why clean |
|---|---|---|
| `01-orphaned-front-internal-cidr` | CLEAN | deep chain orphaned (web accepts the internal mesh CIDR, not the ALB SG) |
| `02-public-alb-no-sg-ref` | CLEAN | loud public ALB intended; nothing references the ALB SG |
| `03-disjoint-public-vpn-islands` | CLEAN | two disconnected islands; data island is VPN-only |
| `04-broken-segment-midchain` | CLEAN | visible chain cut one hop in (web accepts the mesh CIDR, not the edge SG) |
| `05-six-hop-cdn-waf-gw-app-svc-db` | P1 + B1 + H1 | internet -> cdn -> waf -> gw -> app -> svc -> db (6 hops) |
| `06-compromised-ci-runner-deep` | P1 + B1 | ci -> build -> artifact -> deploy -> app -> db (5 hops, compromised-host entry) |
| `07-five-hop-ingress-mesh-broker-db` | P1 + B1 + H1 | internet -> ingress -> mesh -> app -> broker -> db (5 hops) |

Mix: 4 deceptive/segmented-clean, 3 buried-deep needles. Each fixture is a high-volume fleet
(10-13 SGs).

## Run

```bash
export ANTHROPIC_API_KEY=...
pip install anthropic
python tests/eval/run_eval.py --trials 3                 # full screening (~42 LLM calls)
python tests/eval/run_eval.py --trials 1 --fixtures 01,02 # smoke test
python tests/eval/run_eval.py --trials 3 --fresh          # ignore prior results
```

Defaults: `--trials 3`, agent + judge `claude-sonnet-4-6`, results in `eval_results.json`.
Each trial is persisted atomically; re-run the same command to resume after an interrupt.

## Ground truth offline (no key)

```bash
python tests/eval/scenarios.py   # prints needle path + hop count / clean / blast radius per fixture
```

The judge is anchored to `scenarios.expected_deep()`, which runs the reused deterministic
engine. The two load-bearing rubric items are **item 2** (surfaces the buried long needle as
a primary finding, hops named end to end, not only the obvious surface items) and **item 3**
(does not over-flag the benign / neutralised bait — the orphaned deep chain in `01`, the
intended public ALB in `02`, the disconnected data island in `03`, the broken chain in `04`).
See `rubric.md` and `judge_prompt.md`.

## Verdict (from control means only)

- aggregate `< 4.0/7` or a majority of fixtures `< 4.0` -> **BUILD**
- aggregate `< 5.5/7` -> **MAYBE**
- otherwise -> **SKIP**

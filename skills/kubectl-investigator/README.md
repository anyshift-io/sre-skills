# kubectl-investigator

Methodology-shaped SRE skill for investigating a live or recent incident on **Kubernetes**.

Anchors the incident window, bisects the change surface (rollouts, ConfigMaps/Secrets, RBAC, HPA/cluster changes, CronJobs), classifies the failure against four reference paths (OOM, DNS, cascading-failure, deploy-correlator), confirms with three independent signals, quantifies blast radius, and proposes mitigation before root cause.

## Files in this skill

| File | What it is |
|---|---|
| [`SKILL.md`](./SKILL.md) | The methodology. This is what an AI agent loads. |
| [`examples/`](./examples/) | Eleven worked examples covering the four reference paths, the FAILURE_MODES escalation rules, and edge cases. |
| [`fixtures/`](./fixtures/) | Committed telemetry / event snapshots (pod events, metrics, logs, traces, rollout/RBAC/cluster changes) that drive the replay tests. No live cluster or credentials required. |
| [`tests/`](./tests/) | Replay tests that exercise the methodology against the fixtures. |
| [`FAILURE_MODES.md`](./FAILURE_MODES.md) | Where this skill is wrong and where the agent should escalate. |

## Quality bar (this skill passes all three)

- [x] Two worked examples required by the bar; this skill ships [eleven](./examples/) covering the four reference paths, the FAILURE_MODES escalation rules, and edge cases.
- [x] Fixture-based replay tests, runnable with no live cluster or credentials. 99 assertions across the 11 tests (`for t in tests/replay_*.py; do python "$t" || exit 1; done`).
- [x] Explicit failure-modes section ([`FAILURE_MODES.md`](./FAILURE_MODES.md)).

## Measured lift

An LLM ablation eval is committed under [`tests/eval/`](./tests/eval/). An automated run with Claude Sonnet 4.6 as both agent and LLM-judge (**N=3 trials per cell**, 66 trials, scored against the 7-item rubric in [`rubric.md`](./tests/eval/rubric.md)) measured a **+0.82 / 7 (+15%) lift** of an agent loaded with this `SKILL.md` (mean 6.36) over an agent given the same telemetry with no methodology (mean 5.55). Treatment wins on 9 of 11 fixtures, ties on 2, and **loses on none**; the largest lifts are on the escalation cases the cold agent doesn't know to guard against (third-party rate-limit +2.33, confirmation-bias +1.67, capacity-bound +1.33). See [`tests/eval/README.md`](./tests/eval/README.md) for the full per-fixture table and the honest caveats on the methodology. Reproduce with `python tests/eval/run_eval.py --trials 3`.

## How to use

### As a Claude Code / Claude Skills user

Drop `skills/kubectl-investigator/` into your skills directory and invoke when a Kubernetes incident is in progress. The agent reads `SKILL.md` and follows the methodology end-to-end against your cluster telemetry (kubectl, the events API, kube-state-metrics, Prometheus).

### As a contributor adding a new reference path or example

1. Add a new example file under `examples/` mirroring the existing ones.
2. Commit fixtures under `fixtures/<example-slug>/` (pod events, metrics, traces, logs, rollout/RBAC/cluster changes as relevant).
3. Add a replay test under `tests/replay_NN_<example-slug>.py` that asserts the methodology produces the correct classification + mitigation.
4. Update [`SKILL.md`](./SKILL.md) if the new path is reference-quality (i.e. covers >5% of real Kubernetes incidents); otherwise keep it in `examples/` only.

See the top-level [`CONTRIBUTING.md`](../../CONTRIBUTING.md) for the repo-wide bar.

## Anyshift integration (opt-in)

The methodology runs vendor-neutral by default (any cluster, kubectl + your telemetry). Opting in to the [Anyshift MCP](https://www.anyshift.io) for step 2 (change-surface bisection) gives the agent a versioned resource graph that links rollouts, RBAC changes, and cluster/infrastructure changes to the Kubernetes resources implicated in the incident.

A measured "with vs without" delta will be published in this section once the MCP integration has been exercised against the replay tests above. Numbers will replace this note directly.

## License

[Apache 2.0](../../LICENSE).

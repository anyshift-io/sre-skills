# incident-investigator

Methodology-shaped SRE skill for investigating a live or recent incident.

Anchors the incident window, bisects the change surface, classifies the failure against four reference paths (OOM, DNS, cascading-failure, deploy-correlator), confirms with three independent signals, quantifies blast radius, and proposes mitigation before root cause.

## Files in this skill

| File | What it is |
|---|---|
| [`SKILL.md`](./SKILL.md) | The methodology. This is what an AI agent loads. |
| [`examples/`](./examples/) | Eleven worked examples covering the four reference paths, the FAILURE_MODES escalation rules, and edge cases. |
| [`fixtures/`](./fixtures/) | Committed telemetry / deploy event snapshots that drive the replay tests. No external credentials required. |
| [`tests/`](./tests/) | Replay tests that exercise the methodology against the fixtures. |
| [`FAILURE_MODES.md`](./FAILURE_MODES.md) | Where this skill is wrong and where the agent should escalate. |

## Quality bar (this skill passes all three)

- [x] Two worked examples required by the bar; this skill ships [eleven](./examples/) covering the four reference paths, the FAILURE_MODES escalation rules, and edge cases.
- [x] Fixture-based replay tests, runnable with no external credentials. 99 assertions across the 11 tests (`for t in tests/replay_*.py; do python "$t" || exit 1; done`).
- [x] Explicit failure-modes section ([`FAILURE_MODES.md`](./FAILURE_MODES.md)).

## Measured lift

An LLM ablation eval is committed under [`tests/eval/`](./tests/eval/). A reference run with Claude Sonnet 4.6 (N=1, manual scoring against a 7-item rubric) measured **+2.64 / 7 (+38%) lift** of an agent loaded with this `SKILL.md` over an agent given the same telemetry with no methodology. Treatment beats control on every one of the 11 fixtures. See [`tests/eval/README.md`](./tests/eval/README.md) for the full per-fixture table, what changed in `SKILL.md` after the first pass, and the honest caveats on the methodology. Reproduce with `python tests/eval/run_eval.py --trials 5`.

## How to use

### As a Claude Code / Claude Skills user

Drop `skills/incident-investigator/` into your skills directory and invoke when an incident is in progress. The agent reads `SKILL.md` and follows the methodology end-to-end.

### As a contributor adding a new reference path or example

1. Add a new example file under `examples/` mirroring the existing two.
2. Commit fixtures under `fixtures/<example-slug>/` (logs, metrics, traces, deploys, IAM events as relevant).
3. Add a replay test under `tests/replay_NN_<example-slug>.py` that asserts the methodology produces the correct classification + mitigation.
4. Update [`SKILL.md`](./SKILL.md) if the new path is reference-quality (i.e. covers >5% of real incidents); otherwise keep it in `examples/` only.

See the top-level [`CONTRIBUTING.md`](../../CONTRIBUTING.md) for the repo-wide bar.

## Anyshift integration (opt-in)

The methodology runs vendor-neutral by default. Opting in to the [Anyshift MCP](https://www.anyshift.io) for step 2 (change-surface bisection) gives the agent a versioned resource graph that links deploys, IAM changes, and infrastructure changes to the resources implicated in the incident.

A measured "with vs without" delta will be published in this section once the MCP integration has been exercised against the two replay tests above. Numbers will replace this note directly.

## License

[Apache 2.0](../../LICENSE).

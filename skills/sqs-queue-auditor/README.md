# sqs-queue-auditor

Configuration-audit skill for a single AWS SQS queue.

Parses the `GetQueueAttributes` output for one queue (and its referenced dead-letter queue), applies the judgment a senior engineer applies to that one source, and reports the misconfigurations that silently drop or re-deliver messages while every attribute reads as fine. Then it names the boundary: the questions a single queue's config cannot answer.

## Files in this skill

| File | What it is |
|---|---|
| [`SKILL.md`](./SKILL.md) | The methodology. This is what an AI agent loads. |
| [`examples/`](./examples/) | Eight worked examples, one per rule plus a clean control. |
| [`fixtures/`](./fixtures/) | Committed `GetQueueAttributes` snapshots that drive the replay tests. No external credentials required. |
| [`tests/`](./tests/) | Replay tests that exercise the audit against the fixtures. |
| [`FAILURE_MODES.md`](./FAILURE_MODES.md) | Where this skill is wrong and where the agent should escalate. |

## What it checks

| Code | Rule | Severity |
|---|---|---|
| R1 | No dead-letter queue on a processing queue | high |
| R2 | `maxReceiveCount` outside the 3-10 band | medium / low |
| R3 | DLQ retention not longer than source retention | critical |
| R4 | Poison messages age out before reaching the DLQ | critical |
| R5 | Visibility timeout at the 30s default | low |
| R6 | Retention shorter than a plausible outage | medium |
| R7 | Resource policy allows a wildcard principal with no condition | high |
| R8 | Server-side encryption at rest disabled | low |
| R9 | FIFO queue with content-based dedup off | low |

The two critical rules (R3, R4) are the ones a console read almost never catches: both turn a correctly-wired, correctly-sized dead-letter queue into one that silently never receives the messages it was built for.

## Quality bar (this skill passes all three)

- [x] Two worked examples required by the bar; this skill ships [eight](./examples/), one per rule plus a clean control that asserts no false positives.
- [x] Fixture-based replay tests, runnable with no external credentials. 48 assertions across the 8 tests (`for t in tests/replay_*.py; do python "$t" || exit 1; done`).
- [x] Explicit failure-modes section ([`FAILURE_MODES.md`](./FAILURE_MODES.md)).

## Measured lift

An LLM ablation eval is committed under [`tests/eval/`](./tests/eval/). A reference run with Claude Sonnet 4.6 (N=3, LLM-as-judge against the 7-item rubric, on the four most diagnostic fixtures) measured **+3.08 / 7 (+44%) lift** of an agent loaded with this `SKILL.md` over an agent given the same `GetQueueAttributes` JSON with no methodology. Treatment beats control on every fixture and sweeps 7.00 / 7 with zero variance.

The lift concentrates where it should: **no control output produced a boundary section** (every cold agent presented a config read as a full health verdict), and on the clean control the cold agent flagged an `aws:SourceArn`-scoped wildcard policy as a HIGH "public queue", the textbook false positive the skill's R7 precision exists to avoid. See [`tests/eval/README.md`](./tests/eval/README.md) for the per-fixture table, the per-rubric-item breakdown, the R4 over-fire regression the eval caught and the SKILL.md edit that closed it, and the caveats. Reproduce with `python tests/eval/run_eval.py --trials 3`.

## How to use

### As a Claude Code / Claude Skills user

Drop `skills/sqs-queue-auditor/` into your skills directory and invoke when reviewing or hardening a queue. The agent reads `SKILL.md`, parses the queue attributes, and reports findings plus the boundary. Point it at a real queue with `aws sqs get-queue-attributes --queue-url <url> --attribute-names All`, or run it against the committed fixtures first.

### As a contributor adding a new rule or example

1. Add a fixture directory under `fixtures/<example-slug>/` with `queue.json` (and `dlq.json` if the queue has a DLQ), following the `GetQueueAttributes` shape in [`tests/README.md`](./tests/README.md).
2. Add a worked example under `examples/` mirroring the existing eight.
3. Add a replay test under `tests/replay_NN_<slug>.py` asserting the expected findings and that the boundary is reported.
4. Update [`SKILL.md`](./SKILL.md) and this table if the rule is new.

See the top-level [`CONTRIBUTING.md`](../../CONTRIBUTING.md) for the repo-wide bar.

## Anyshift integration (opt-in)

The audit runs vendor-neutral by default. Every boundary note this skill emits is a join it cannot make from one queue's attributes: queue to its consumers, queue to its CloudWatch metrics over time, queue to the account's IAM graph, queue to the producers and consumers on either side. Opting in to the [Anyshift MCP](https://www.anyshift.io) resolves those joins from a versioned resource graph, so a deferred flag becomes a closed finding.

A measured "with vs without" delta will be published here once the MCP integration has been exercised against the replay fixtures.

## License

[Apache 2.0](../../LICENSE).

# Replay tests for `sqs-queue-auditor`

Stdlib-only Python tests that exercise the audit in [`../SKILL.md`](../SKILL.md) against committed fixtures. No external credentials required.

## Running the tests

From the skill directory (`skills/sqs-queue-auditor/`):

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

Each test prints `PASS` or `FAIL` and exits with the appropriate code. The current suite has 8 tests covering all nine rules (R1-R9), the severity model, and a clean control that asserts no false positives, totalling 48 assertions. Wire them into CI as plain `python` invocations.

## What the tests assert

Each replay test loads the fixtures for one worked example, runs the reference audit (`_audit.py`) against them, and asserts:

- The queue is parsed correctly (ARN, FIFO flag, DLQ presence).
- The expected rule(s) fire, and only those (each example isolates a rule, except where two genuinely co-occur).
- The severity is correct (the critical rules R3 / R4 are asserted critical; the soft flags R5 / R8 / R9 are asserted low).
- The boundary is reported, and names the specific join the example depends on (consumer time, IAM union, producer contract).

A test fails when the audit regresses on any of these. Treat a failed replay test as a regression in `SKILL.md` or in the reference implementation, not a test bug.

## Fixture schema

Each example has its own fixture directory under `../fixtures/<example-slug>/`. Files mirror the real AWS `GetQueueAttributes` response: a single JSON object with an `Attributes` map whose values are **all strings**, and whose compound attributes (`RedrivePolicy`, `Policy`, `RedriveAllowPolicy`) are JSON documents **encoded as strings**.

| File | Required | Purpose |
|---|---|---|
| `queue.json` | yes | The source queue's `GetQueueAttributes` output. |
| `dlq.json` | when the queue has a DLQ | The dead-letter queue's `GetQueueAttributes` output. Needed for the R3 retention-ordering check; its ARN is the source queue's `RedrivePolicy.deadLetterTargetArn`. |

Key attributes the audit reads:

| Attribute | Type (as stored) | Used by |
|---|---|---|
| `QueueArn` | string | identification |
| `VisibilityTimeout` | string seconds | R4, R5 |
| `MessageRetentionPeriod` | string seconds | R3, R4, R6 |
| `RedrivePolicy` | JSON string (`deadLetterTargetArn`, `maxReceiveCount`) | R1, R2, R3, R4 |
| `Policy` | JSON string (IAM policy document) | R7 |
| `SqsManagedSseEnabled` / `KmsMasterKeyId` | string / string | R8 |
| `FifoQueue` / `ContentBasedDeduplication` | string booleans | R9 |

The reference implementation (`_audit.py`) accepts either the full `{"Attributes": {...}}` envelope or a bare attribute map, and treats a missing `dlq.json` as "DLQ attributes not provided" (R3 skipped).

## Adding a new replay test

When you contribute a new worked example to the skill:

1. Drop fixtures under `../fixtures/<example-slug>/` following the schema above.
2. Add `replay_NN_<slug>.py` in this directory, modeled on the existing eight. Use the shared `report` helper in `_replay.py`.
3. Assert the expected findings, the severity, and that the boundary names the relevant join.
4. Run locally, commit, and reference the test in the example's markdown narrative.

A new test that does not exercise a rule, severity, or boundary join the existing tests do not exercise will fail review. The point of the replay corpus is breadth.

## Why stdlib only

Skills get adopted when they run anywhere with zero setup. A `pip install` is an adoption tax. The reference implementation uses only `json`, `pathlib`, `dataclasses`, and `typing`. If a future test requires a third-party dependency (e.g. `boto3` or `pytest`), that's a signal the skill is leaking implementation detail: the audit operates on the `GetQueueAttributes` output, not on a live AWS connection.

## Why the reference implementation is deterministic

`_audit.py` is a deterministic stand-in for what an AI agent does when it follows `SKILL.md`. It exists so the replay tests can assert that the methodology, applied to known fixtures, produces the expected findings. A natural follow-up is to run the same fixtures through an actual LLM agent loaded with `SKILL.md` and assert it produces the same findings and names the same boundary; that work is out of scope for the first reference skill.

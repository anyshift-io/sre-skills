# Worked example 4: poison messages age out before the DLQ (R4)

The flagship. A dead-letter queue that is present, sized with generous retention, and never receives a single poison message, because of an arithmetic relationship between three attributes that nobody checks by hand. Fixtures and replay test under `../fixtures/04-poison-ages-out-before-dlq/` and `../tests/replay_04_poison_ages_out.py`.

## Scenario

- **Queue**: `ledger-reconcile`, with DLQ `ledger-reconcile-dlq`.
- **Symptom**: a daily reconciliation job has a recurring poison record. The DLQ was built specifically to catch it. The DLQ is always empty. The poison record is being silently deleted by retention before it ever reaches the DLQ.

## Step 1: parse the attributes

Source (`queue.json`):
```
VisibilityTimeout      900      (15 minutes)
MessageRetentionPeriod 345600   (4 days)
RedrivePolicy          {"deadLetterTargetArn":"...:ledger-reconcile-dlq","maxReceiveCount":1000}
```
DLQ (`dlq.json`):
```
MessageRetentionPeriod 1209600  (14 days)
```

`VisibilityTimeout=900`, `maxReceiveCount=1000`, `MessageRetentionPeriod=345600`.

## Step 2: audit the redrive path

The DLQ is present, and its 14-day retention exceeds the source's 4 days, so R3 does not fire. But `maxReceiveCount=1000` is above the sane band, raising **R2 (low)**: a poison message would be retried up to a thousand times before quarantine. That is the warning. The next check is the bug.

## Step 3: audit the message lifecycle

A poison message needs at least `maxReceiveCount x VisibilityTimeout` seconds of wall-clock to exhaust its receive count and dead-letter:

```
1000 x 900 = 900000 seconds  (about 10.4 days)
```

But `MessageRetentionPeriod` is `345600` seconds (4 days). Retention wins. The message is deleted by age after 4 days, having reached only about 384 of its 1000 receives, long before it is eligible for the DLQ. That is **R4 (critical)**. The dead-letter queue exists, is wired, and has generous retention, and the exact message it was built to catch never arrives in it.

This is pure arithmetic on three static attributes. It is almost never done by hand, because each attribute looks reasonable in isolation: a 15-minute visibility timeout for a slow job is sensible, a high `maxReceiveCount` for a flaky dependency is defensible, a 4-day retention is the default. The failure is in their product.

## Steps 4-5: exposure, FIFO

Clean. Visibility is a deliberate 900s (no R5), retention is the default (no R6), SSE is on, no resource policy, standard queue.

## Findings

| Code | Severity | Attribute | Fix |
|---|---|---|---|
| R4 | critical | `VisibilityTimeout` x `maxReceiveCount` vs `MessageRetentionPeriod` | Lower `maxReceiveCount` or `VisibilityTimeout`, or raise `MessageRetentionPeriod`, so `maxReceiveCount x VisibilityTimeout` stays well under retention. |
| R2 | low | `RedrivePolicy.maxReceiveCount` | Lower `maxReceiveCount` into the 3-10 band unless a specific replay requirement justifies more. Lowering it also resolves R4. |

## Boundary

The audit proves a poison message *cannot* reach the DLQ in time. It cannot confirm a poison message currently exists.

- Whether the reconciliation job is dead-lettering anything is the source queue's age-of-oldest-message and the consumer's per-message receive count, both time-series. Join: queue to its metrics over time.
- The real time-to-DLQ depends on how often a consumer actually receives the message (the arithmetic is a lower bound). Join: queue to its consumers.

## Why this is the R4 reference

R4 is the rule that most justifies the skill. The DLQ is present and correctly sized on every dimension a checklist would inspect; the failure is an interaction between three attributes that only a deliberate calculation surfaces. An agent with raw `GetQueueAttributes` access does not perform this multiplication zero-shot. The judgment is the multiplication and the comparison against retention.

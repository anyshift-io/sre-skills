# Worked example 8: a clean queue (control)

A correctly-configured queue. The audit produces zero findings, does not invent one, and still reports its boundary. This control is what keeps the skill trustworthy: an auditor that flags clean configs is one operators learn to ignore. Fixtures and replay test under `../fixtures/08-clean-standard/` and `../tests/replay_08_clean_standard.py`.

## Scenario

- **Queue**: `notification-fanout`, with DLQ `notification-fanout-dlq`. Subscribed to an SNS topic, processed by a worker fleet.

## Step 1: parse the attributes

```
VisibilityTimeout      180      (deliberate, not the 30s default)
MessageRetentionPeriod 345600   (4 days)
SqsManagedSseEnabled   true
Policy                 Allow Principal:"*" SendMessage,
                       Condition ArnEquals aws:SourceArn = ...:sns:account-events
RedrivePolicy          {"deadLetterTargetArn":"...:notification-fanout-dlq","maxReceiveCount":5}
```
DLQ (`dlq.json`):
```
MessageRetentionPeriod 1209600  (14 days)
```

## Steps 2-5: every check passes

- **Redrive (R1/R2/R3)**: DLQ present; `maxReceiveCount=5` in band; DLQ retention (14 days) is longer than the source (4 days). Clean.
- **Lifecycle (R4/R5/R6)**: `5 x 180 = 900s`, far under the 4-day retention, so poison messages reach the DLQ with room to spare. Visibility is a deliberate 180s, not the default. Retention is the 4-day default. Clean.
- **Exposure (R7/R8)**: the resource policy uses `Principal: "*"` **but narrows it** with `aws:SourceArn` pinned to the SNS topic. This is the standard, correct SNS-to-SQS pattern, so R7 does **not** fire. SSE is on, so R8 does not fire. Clean.
- **FIFO (R9)**: standard queue, not FIFO. Not applicable.

No findings.

## Boundary

A clean configuration is not a clean system. Even here, the audit reports what it cannot see:

- The queue could still be failing right now (a crashing consumer, a producer that stopped) for a reason only the live metrics show. Join: queue to its metrics over time.
- The effective access is still the union of this scoped resource policy and the account's identity policies. Join: queue to the account's IAM graph.
- Whether anyone is draining the DLQ is still unknown. Join: DLQ to its owner.

## Why this is the control

It pins two behaviours the other seven examples cannot: that the skill produces **zero** findings on a correct queue (no false positives), and specifically that a wildcard principal scoped by `aws:SourceArn` is recognised as legitimate and not flagged as R7. It also makes the boundary point unmissable: the audit reports the join it cannot make even when there is nothing to fix, because a sound config and a healthy system are different claims.

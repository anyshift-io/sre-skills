# Worked example 2: DLQ retention shorter than the source (R3)

A dead-letter queue that is wired correctly, sized correctly on `maxReceiveCount`, and still silently deletes the messages you most need to see. This is the skill's defining check: it depends on one piece of SQS semantics that is easy to get wrong. Fixtures and replay test under `../fixtures/02-dlq-retention-shorter-than-source/` and `../tests/replay_02_dlq_retention.py`.

## Scenario

- **Queue**: `order-events`, with DLQ `order-events-dlq`.
- **Symptom**: during an incident, an engineer opens the DLQ to inspect the failed orders. It is nearly empty, even though the source queue clearly dead-lettered a batch an hour ago. The messages arrived in the DLQ and were deleted within minutes.

## Step 1: parse the attributes

Source (`queue.json`):
```
MessageRetentionPeriod 345600   (4 days)
RedrivePolicy          {"deadLetterTargetArn":"...:order-events-dlq","maxReceiveCount":5}
```
DLQ (`dlq.json`):
```
QueueArn               ...:order-events-dlq
MessageRetentionPeriod 86400    (1 day)
```

The `RedrivePolicy` is a JSON string; parsing it gives the DLQ ARN and `maxReceiveCount=5` (in band, so no R2). The retention check needs the DLQ's *own* attributes, which is why `dlq.json` must be loaded.

## Step 2: audit the redrive path

`maxReceiveCount=5` is healthy. The DLQ exists. But the source retains for 4 days and the DLQ retains for 1 day, so `dlq_retention (86400) <= source_retention (345600)`. That is **R3 (critical)**.

The mechanism is the part that catches people: **a message's age is measured from its original `SentTimestamp`, and SQS does not reset that timestamp when the message is moved to the DLQ.** A message that sits in `order-events` for 3 days before finally exhausting its 5 receives arrives in the DLQ already 3 days old. The DLQ's retention is 1 day. The message is over the limit the instant it arrives, and SQS deletes it. The DLQ looks perfectly configured. It catches nothing that failed slowly.

## Steps 3-5: lifecycle, exposure, FIFO

Clean. `5 x 60 = 300s` is far below the 4-day retention (no R4). Visibility is a deliberate 60s (no R5), retention is the default (no R6), SSE is on, no resource policy, standard queue. R3 is the only finding.

## Finding

| Code | Severity | Attribute | Fix |
|---|---|---|---|
| R3 | critical | source vs DLQ `MessageRetentionPeriod` | Set the DLQ's `MessageRetentionPeriod` above the source's, ideally to the 14-day maximum (`1209600`), so failed messages survive long enough to inspect and redrive. |

## Boundary

The audit proves the DLQ *can* delete messages on arrival. It cannot tell you whether it already has.

- How many messages were dropped this way, and when, is the DLQ's delete/redrive metrics over time, not a static attribute. Join: DLQ to its metrics over time.
- Whether anything is draining the DLQ at all is a property of the operational owner, not the queue. Join: DLQ to its owner.

## Why this is the R3 reference

Every visible signal says the dead-letter path is correct: a DLQ is attached, `maxReceiveCount` is sane, the DLQ even has messages arriving. The bug is a single inequality between two retention periods, made lethal by a non-obvious SQS semantic (the timestamp does not reset on redrive). It is exactly the judgment a config read should carry and a console glance does not.

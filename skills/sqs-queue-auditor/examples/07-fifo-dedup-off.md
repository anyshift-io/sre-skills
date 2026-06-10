# Worked example 7: FIFO queue with content-based deduplication off (R9)

A FIFO queue whose exactly-once guarantee rests entirely on a contract the queue cannot enforce: that every producer supplies a deduplication ID. Fixtures and replay test under `../fixtures/07-fifo-dedup-off/` and `../tests/replay_07_fifo_dedup_off.py`.

## Scenario

- **Queue**: `inventory-updates.fifo`, with DLQ `inventory-updates-dlq.fifo`.
- **Context**: a FIFO queue chosen for ordering and exactly-once processing of stock adjustments. `ContentBasedDeduplication` is off.

## Step 1: parse the attributes

```
QueueArn                   ...:inventory-updates.fifo
FifoQueue                  true
ContentBasedDeduplication  false
RedrivePolicy              {"deadLetterTargetArn":"...:inventory-updates-dlq.fifo","maxReceiveCount":5}
```

The `.fifo` suffix and `FifoQueue=true` mark this as a FIFO queue, so the FIFO invariants apply.

## Step 5: audit FIFO invariants

`ContentBasedDeduplication` is off, which is **R9 (low)**. With content-based dedup off, SQS does not derive a deduplication ID from the message body. The 5-minute deduplication guarantee therefore depends entirely on every producer supplying an explicit `MessageDeduplicationId`. If any producer omits it, two sends of the same stock adjustment within the dedup window are accepted as distinct messages, and the inventory is decremented twice.

Whether the producers actually send the ID is **a property of the producers, not of this queue**. The queue cannot enforce it and the audit cannot see it. So R9 is surfaced low and deferred to the boundary: the contract is flagged for verification, not asserted as broken.

## Steps 2-4: redrive, lifecycle, exposure

Clean. DLQ present, `maxReceiveCount=5` in band, DLQ retention (14 days) exceeds source (4 days). `5 x 120 = 600s` under retention. Visibility deliberate at 120s, retention default, SSE on, no resource policy. R9 is the only finding.

## Finding

| Code | Severity | Attribute | Fix |
|---|---|---|---|
| R9 | low | `ContentBasedDeduplication` | Either enable `ContentBasedDeduplication`, or confirm every producer sets `MessageDeduplicationId`. |

## Boundary

The audit proves the queue relies on a producer-supplied dedup ID. It cannot confirm the producers supply one.

- Whether each producer sends `MessageDeduplicationId` is producer code, not a queue attribute. Join: queue to its producers.
- Whether duplicates have actually been accepted is the sent/dedup-reject metrics over time. Join: queue to its metrics over time.

## Why this is the R9 reference

It is a third instance of the skill's honest-flag pattern (alongside R5 and R8): a real risk, grounded in a real attribute, whose confirmation lives on the other side of the boundary. The skill states the dependency and the fix, and stops at the wall instead of guessing whether the producers are well-behaved.

# Worked example 5: default visibility timeout and short retention (R5, R6)

Two soft flags on one queue. Neither is a confirmed message-loss bug from the config alone; both are defaults that are usually accidental rather than chosen, and both defer their final verdict to something behind the boundary. This example exists to show the skill's honesty: it flags without overclaiming. Fixtures and replay test under `../fixtures/05-default-visibility-short-retention/` and `../tests/replay_05_default_visibility.py`.

## Scenario

- **Queue**: `click-events`, with DLQ `click-events-dlq`.
- **Context**: a high-volume analytics ingest queue. Two attributes look like they were never set deliberately.

## Step 1: parse the attributes

```
VisibilityTimeout      30       (the AWS default)
MessageRetentionPeriod 300      (5 minutes)
RedrivePolicy          {"deadLetterTargetArn":"...:click-events-dlq","maxReceiveCount":5}
```

## Step 2: audit the redrive path

DLQ present, `maxReceiveCount=5` in band, DLQ retention (14 days) far exceeds source (5 minutes). No R2, no R3.

## Step 3: audit the message lifecycle

- `VisibilityTimeout=30` is the AWS default. That raises **R5 (low)**. If any consumer takes longer than 30 seconds to process a click event, the message becomes visible again mid-processing and is delivered to a second consumer, causing duplicate work. Whether that actually happens depends on the consumer's processing time, **which is not a queue attribute**. So this is a flag to verify, not a confirmed bug, and it is surfaced as low severity for exactly that reason.
- `MessageRetentionPeriod=300` (5 minutes) raises **R6 (medium)**. Any consumer outage, deploy, or scaling lag longer than 5 minutes silently drops every queued message. For an analytics ingest that may be an acceptable trade (stale clicks are worthless), or it may be an accident. The config flags it; the operator decides.
- R4 does not fire: `5 x 30 = 150s`, under the 300s retention (barely, which is itself worth noting to the operator).

## Steps 4-5: exposure, FIFO

Clean. SSE on, no resource policy, standard queue.

## Findings

| Code | Severity | Attribute | Fix |
|---|---|---|---|
| R6 | medium | `MessageRetentionPeriod` | Raise retention to cover the longest plausible consumer outage, unless dropping stale messages is the intended behaviour. |
| R5 | low | `VisibilityTimeout` | Set the visibility timeout deliberately, above the consumer's p99 processing time, if duplicate delivery matters. |

## Boundary

Both findings defer to something the queue does not contain.

- Whether the 30s visibility timeout is actually too short is the consumer's processing-time distribution, not a queue attribute. Join: queue to its consumers.
- Whether the 5-minute retention actually loses messages is the consumer outage history, a time-series. Join: queue to its metrics over time.

## Why this is the R5 / R6 reference

It demonstrates the skill declining to overclaim. R5 in particular could be written as "visibility timeout too short, messages double-processed", but the skill cannot prove that from the config: it depends on consumer behaviour. Flagging it low and naming the join is the correct, honest move. A skill that asserted a bug here would be wrong as often as it was right.

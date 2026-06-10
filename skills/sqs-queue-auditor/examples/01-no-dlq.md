# Worked example 1: no dead-letter queue on a processing queue (R1)

A processing queue with no `RedrivePolicy`. Every attribute reads as healthy, the queue has messages flowing, and a poison message has nowhere to go. Fixtures and replay test under `../fixtures/01-no-dlq/` and `../tests/replay_01_no_dlq.py`.

## Scenario

- **Queue**: `payments-capture`. A worker fleet receives capture events and calls a payment processor.
- **Symptom**: one malformed capture event (a cents value the processor rejects) is received, fails, becomes visible again, and is redelivered. Forever. No alert, no DLQ, no record. After four days it is deleted by retention and nobody ever sees it.

## Step 1: parse the attributes

```
QueueArn               arn:aws:sqs:eu-west-1:211125758836:payments-capture
VisibilityTimeout      120
MessageRetentionPeriod 345600   (4 days, the default)
RedrivePolicy          (absent)
SqsManagedSseEnabled   true
```

`VisibilityTimeout` is a deliberate 120s (not the 30s default, so R5 does not fire). Retention is the 4-day default (R6 does not fire). SSE is on (R8 does not fire). The one thing missing is the `RedrivePolicy`.

## Step 2: audit the redrive path

No `RedrivePolicy` means no dead-letter queue. On a processing queue, that is **R1 (high)**. A poison message is received, fails, and after `VisibilityTimeout` becomes visible again. It is retried on every cycle for the full `MessageRetentionPeriod`, burning a consumer slot each time, and is then deleted silently. There is no quarantine and no signal. The only evidence the message ever existed is a worker that spent four days failing on it.

## Steps 3-5: lifecycle, exposure, FIFO

All clean. Visibility is deliberate, retention is the default, the queue is encrypted, there is no resource policy, and the queue is standard (not FIFO). R1 is the only finding.

## Finding

| Code | Severity | Attribute | Fix |
|---|---|---|---|
| R1 | high | `RedrivePolicy` absent | Attach a `RedrivePolicy` to a DLQ with `maxReceiveCount` in the 3-10 band, so poison messages are quarantined instead of dropped. |

## Boundary

The audit confirms there is nowhere for failed messages to go. It cannot tell you whether any message is *currently* failing: that is the redrive metric and the consumer error rate, both behind the boundary.

- Whether a poison message is in the queue right now is `ApproximateAgeOfOldestMessage` and the consumer error rate over time, not a static attribute. Join: queue to its metrics over time.
- Whether this queue is genuinely a processing queue (R1) or a buffer with an at-least-once contract elsewhere is a property of the architecture, not the queue. Join: queue to its consumers.

## Why this is the R1 reference

It is the cleanest possible R1: a single missing attribute on an otherwise healthy queue, with a failure mode (silent four-day drop of poison messages) that no console glance surfaces because every visible number looks fine.

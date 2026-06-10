# Worked example 3: maxReceiveCount too low (R2)

A dead-letter queue wired correctly, sized correctly on retention, and set to give up after a single failed delivery. Transient blips dead-letter perfectly good messages. Fixtures and replay test under `../fixtures/03-maxreceivecount-too-low/` and `../tests/replay_03_maxreceivecount.py`.

## Scenario

- **Queue**: `email-dispatch`, with DLQ `email-dispatch-dlq`.
- **Symptom**: the DLQ has over a thousand messages in it. On inspection, almost all of them are valid emails that would have sent fine on a retry. A 90-second SES throttle this morning dead-lettered every message in flight, because the queue gives up after one attempt.

## Step 1: parse the attributes

Source (`queue.json`):
```
MessageRetentionPeriod 345600   (4 days)
RedrivePolicy          {"deadLetterTargetArn":"...:email-dispatch-dlq","maxReceiveCount":1}
```
DLQ (`dlq.json`):
```
MessageRetentionPeriod 1209600  (14 days)
```

`maxReceiveCount` parses to `1`.

## Step 2: audit the redrive path

The DLQ is present and its retention (14 days) is longer than the source (4 days), so R3 does not fire. But `maxReceiveCount=1` is below the sane band, which is **R2 (medium)**. A message that fails its single delivery attempt goes straight to the DLQ. There is no retry, so any recoverable, transient downstream failure (a rolling deploy, a brief throttle, a 2-second timeout) sends a good message to dead-letter. The DLQ fills with messages that were never poison, which masks the ones that are: when something is genuinely broken, it is buried under a thousand false positives.

## Steps 3-5: lifecycle, exposure, FIFO

Clean. `1 x 60 = 60s` is far below retention (no R4). Visibility is a deliberate 60s (no R5), retention is the default (no R6), SSE is on, no resource policy, standard queue. R2 is the only finding.

## Finding

| Code | Severity | Attribute | Fix |
|---|---|---|---|
| R2 | medium | `RedrivePolicy.maxReceiveCount` | Raise `maxReceiveCount` into the 3-10 band so transient failures are retried before quarantine. |

## Boundary

The audit proves the queue dead-letters on the first failure. It cannot tell you what fraction of the DLQ is transient-failure noise versus genuine poison.

- The ratio of recoverable to poison messages in the DLQ is a property of the message contents and the consumer's failure reasons, not a queue attribute. Join: DLQ to its consumers.
- Whether a redrive of the DLQ would now succeed is the downstream's current health, not a static attribute. Join: queue to its metrics over time.

## Why this is the R2 reference

It is the opposite failure from a missing DLQ: the dead-letter path works *too eagerly*. The fix is a single integer, but the symptom (a DLQ full of valid messages, the real poison invisible inside it) looks like a content problem until you read the one attribute that explains it.

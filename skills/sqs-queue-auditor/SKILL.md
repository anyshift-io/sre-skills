---
name: sqs-queue-auditor
description: Audit a single AWS SQS queue's configuration for the misconfigurations that silently drop or re-deliver messages while every attribute reads as fine. Parses the GetQueueAttributes output (and the referenced dead-letter queue), checks the redrive path (DLQ present, maxReceiveCount band, DLQ-vs-source retention ordering), the message lifecycle (poison messages aging out before they reach the DLQ, default visibility timeout, short retention), and exposure (open resource policy, encryption at rest, FIFO dedup contract). Reports findings with severity and a recommendation, then names the boundary: the questions a single queue's config cannot answer (consumer processing time, live behaviour, the IAM union, the producers and consumers on either side). Use when asked to review, harden, or sanity-check an SQS queue, or to explain why messages are going missing. Vendor-neutral; runs offline against the queue attributes with no Anyshift account.
---

# sqs-queue-auditor

Configuration-audit skill for a single AWS SQS queue. Takes the `GetQueueAttributes` output for one queue, applies the judgment a senior engineer applies to that one source (the thresholds, the known-bad combinations, the one arithmetic relationship that turns a correct-looking config into silent message loss), and returns a ranked list of findings with recommendations. Then it names exactly where a single queue's configuration stops being able to answer the question.

## When to invoke

- An agent is asked to review, harden, or sanity-check an SQS queue before or after it ships.
- Messages are going missing or being processed twice and nobody can see why from the console.
- A dead-letter queue is configured but empty during an incident, and the question is whether it is actually wired to catch what is failing.
- A queue is being added to a Terraform module or a CDK stack and the config should be checked against the known-bad combinations before apply.

## What this skill reads, and what it does not

It reads the static configuration of **one queue**, plus the attributes of the **dead-letter queue that queue's own RedrivePolicy points at**. Both are SQS control-plane reads (`GetQueueAttributes`). That is the entire input. The audit is correct and complete *for what a queue's configuration can tell you*, and it is explicit about the rest:

- It does **not** read CloudWatch. Live behaviour (redrive volume, age of the oldest message, in-flight count, empty-receive rate) is a time-series, not an attribute.
- It does **not** read the consumers. Whether the visibility timeout is actually long enough is a property of how long the consumer takes, which is not in the queue.
- It does **not** read account IAM. The effective set of principals that can act on the queue is the union of the resource policy (visible) and every identity policy in the account (not visible here).
- It does **not** read the producers. Whether the right services are writing to the queue, and whether anyone is draining the DLQ, needs the inventory on either side.

Every audit ends by naming these. The boundary is the same one every time: the join across resources, across sources, or across time.

## The methodology, in order

### 1. Parse the attributes

`GetQueueAttributes` returns every value as a string, and the compound attributes are JSON documents encoded *inside* those strings. Before any judgment:

- Parse `RedrivePolicy` (a JSON string) into `deadLetterTargetArn` and `maxReceiveCount`. A queue with no `RedrivePolicy` has no DLQ.
- Parse `MessageRetentionPeriod`, `VisibilityTimeout`, `DelaySeconds` as integer seconds (they arrive as strings).
- Parse `Policy` (a JSON string) into IAM statements, if present.
- Read `FifoQueue`, `ContentBasedDeduplication`, `SqsManagedSseEnabled`, `KmsMasterKeyId`.
- If a DLQ is referenced, load *its* attributes too. The retention-ordering check is impossible without them.

A naive read skips the embedded JSON entirely and never sees the redrive wiring. Parsing it is step zero of the judgment.

### 2. Audit the redrive path

The dead-letter path is where messages are supposed to go when processing fails. Three things break it:

- **No DLQ on a processing queue (R1).** Without a `RedrivePolicy`, a poison message is retried until `MessageRetentionPeriod` expires, then deleted with no signal. There is no quarantine.
- **maxReceiveCount out of band (R2).** Below 3, a transient downstream blip dead-letters good messages. Above 10, poison messages are retried many times before quarantine, delaying detection and feeding R4. The sane band is roughly 3 to 10.
- **DLQ retention not longer than the source (R3).** A message's age is measured from its original `SentTimestamp`, and SQS does **not** reset that timestamp when the message moves to the DLQ. If the DLQ's retention is less than or equal to the source's, a message that fails late in the source's window arrives in the DLQ already near its age limit and is deleted almost immediately. The DLQ looks wired and sized; the messages you most need to inspect are the ones it drops. This is the single most important non-obvious check in the skill.

### 3. Audit the message lifecycle

Three queue-side timing relationships, all derivable from the static config:

- **Poison messages age out before the DLQ (R4).** A poison message needs at least `maxReceiveCount x VisibilityTimeout` seconds of wall-clock to exhaust its receive count and dead-letter. If that product exceeds `MessageRetentionPeriod`, retention wins: the message is deleted by age before it ever reaches the DLQ. The DLQ is configured but unreachable for slow failures. This is pure arithmetic on three attributes and is almost never checked by hand. Fire R4 **only on the configured-value inequality** (`maxReceiveCount x VisibilityTimeout > MessageRetentionPeriod`); do not raise it speculatively because backlog or load "might" stretch the wall-clock. The product is already a lower bound, so a config that satisfies the inequality is safe by construction. Queue depth and receive cadence are behind the boundary, not inputs to this check.
- **Visibility timeout at the 30s default (R5).** A risk flag, not a proven bug. If a consumer takes longer than 30s, the message reappears mid-processing and is delivered twice. Whether that happens depends on consumer processing time, which is not a queue attribute. Surfaced as low severity and deferred to the boundary.
- **Retention shorter than a plausible outage (R6).** Retention below an hour means a brief consumer outage, deploy, or scaling lag silently drops every message still queued.

### 4. Audit exposure

- **Open resource policy (R7).** A `Policy` statement that allows a wildcard principal (`"*"`) with no narrowing `Condition` (`aws:SourceArn`, `aws:SourceAccount`, `aws:PrincipalOrgID`) authorises any AWS principal to act on the queue. This is the confused-deputy and public-queue exposure. A wildcard principal *with* a `SourceArn` condition (the standard SNS-to-SQS pattern) is fine and must not be flagged.
- **Encryption at rest disabled (R8).** Neither SQS-managed SSE nor a KMS key configured. Low severity, because whether it matters depends on the data classification, which the queue does not carry.

### 5. Audit FIFO invariants

- **FIFO with content-based dedup off (R9).** When `ContentBasedDeduplication` is off on a FIFO queue, every producer must supply an explicit `MessageDeduplicationId` or duplicate sends are accepted as distinct. Whether the producers actually do this is a property of the producers, not the queue. Flagged low and deferred to the boundary.

### 6. Rank and report, then name the boundary

Order findings by severity (critical, high, medium, low). For each: the rule, the attribute(s) it is grounded in, what breaks, and the fix. Then list the boundary: the joins this audit cannot make. A clean config still gets a boundary section, because a clean config is not a clean system.

## Severity model

| Severity | Meaning |
|---|---|
| **critical** | A configuration that silently loses messages. R3 and R4. |
| **high** | A configuration that loses messages on a poison input, or exposes the queue. R1, R7. |
| **medium** | A configuration that loses messages under an ordinary operational gap. R2 (too low), R6. |
| **low** | A risk flag whose confirmation needs something behind the boundary. R2 (too high), R5, R8, R9. |

The low band is deliberately honest: those findings depend on consumer processing time, data classification, or producer behaviour, none of which is a queue attribute. The skill flags them for verification rather than asserting a bug it cannot prove.

## Rule reference

| Code | Rule | Severity | Grounded in |
|---|---|---|---|
| R1 | No dead-letter queue on a processing queue | high | `RedrivePolicy` absent |
| R2 | `maxReceiveCount` outside the 3-10 band | medium / low | `RedrivePolicy.maxReceiveCount` |
| R3 | DLQ retention not longer than source retention | critical | source vs DLQ `MessageRetentionPeriod` |
| R4 | Poison messages age out before reaching the DLQ | critical | `VisibilityTimeout` x `maxReceiveCount` vs `MessageRetentionPeriod` |
| R5 | Visibility timeout at the 30s default | low | `VisibilityTimeout` |
| R6 | Retention shorter than a plausible outage | medium | `MessageRetentionPeriod` |
| R7 | Resource policy allows a wildcard principal with no condition | high | `Policy` |
| R8 | Server-side encryption at rest disabled | low | `SqsManagedSseEnabled` / `KmsMasterKeyId` |
| R9 | FIFO queue with content-based dedup off | low | `ContentBasedDeduplication` |

## Output format

The agent's final message in any invocation must include:

1. **Queue**: ARN, standard or FIFO, DLQ wired or not.
2. **Findings**: ranked by severity, each with the rule code, the attribute(s), what breaks, and the recommendation. Or "no findings" for a clean config.
3. **Boundary**: the joins this audit could not make, stated explicitly so the gap is visible instead of silent.

## Worked examples

Eight end-to-end examples are committed under `examples/`, each with fixtures (real `GetQueueAttributes` shape) and a runnable replay test. Each isolates one rule, except where two genuinely co-occur.

- [`examples/01-no-dlq.md`](./examples/01-no-dlq.md): a payments queue with no DLQ; poison messages are retried until retention expiry, then dropped (R1).
- [`examples/02-dlq-retention-shorter-than-source.md`](./examples/02-dlq-retention-shorter-than-source.md): the silent-loss bug; the DLQ retains for less time than the source, so late failures are deleted on arrival (R3).
- [`examples/03-maxreceivecount-too-low.md`](./examples/03-maxreceivecount-too-low.md): `maxReceiveCount=1` dead-letters good messages on the first transient failure (R2).
- [`examples/04-poison-ages-out-before-dlq.md`](./examples/04-poison-ages-out-before-dlq.md): the flagship; a 15-minute visibility timeout and `maxReceiveCount=1000` mean poison messages age out before reaching a correctly-wired DLQ (R4, plus R2).
- [`examples/05-default-visibility-short-retention.md`](./examples/05-default-visibility-short-retention.md): a 30s default visibility timeout and 5-minute retention; two soft flags that defer to the boundary (R5, R6).
- [`examples/06-public-queue-policy.md`](./examples/06-public-queue-policy.md): a resource policy with `Principal: "*"` and no condition, on an unencrypted queue (R7, R8).
- [`examples/07-fifo-dedup-off.md`](./examples/07-fifo-dedup-off.md): a FIFO queue with content-based dedup off, depending on a producer contract the queue cannot verify (R9).
- [`examples/08-clean-standard.md`](./examples/08-clean-standard.md): the control; a correctly-configured queue produces zero findings and still reports its boundary.

## Replay tests

Every example has a replay test in `tests/` that runs the audit against committed fixtures, with no external credentials. Run from the skill directory:

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

The 8 tests cover all nine rules, the severity model, and the clean-control (no false positives), totalling 48 assertions. Tests exit non-zero if the audit produces the wrong findings or drops the boundary. See [`tests/README.md`](./tests/README.md) for the fixture schema and how to add a new replay test.

## Failure modes

This skill is wrong in predictable ways. Read [`FAILURE_MODES.md`](./FAILURE_MODES.md) before relying on it. Highlights:

- It audits configuration, not behaviour. A queue that passes every check can still be failing right now for a reason only CloudWatch shows.
- The R1 "is this a processing queue" judgment is supplied by the caller; a pure buffer queue may legitimately have no DLQ.
- The low-severity flags (R5, R8, R9) cannot be confirmed without the consumer, the data classification, or the producers. They are flags, not verdicts.

## Anyshift integration (opt-in)

The audit above runs end-to-end against the `GetQueueAttributes` output the user already has. No Anyshift dependency.

Every boundary note in this skill is a join: queue to its consumers, queue to its metrics over time, queue to the account's IAM graph, queue to the producers and consumers on either side. The Anyshift MCP can act as a context primer by resolving those joins from a versioned resource graph, so a finding like R5 ("visibility timeout at default, verify against consumer processing time") or R7 ("resource policy is half the access story") can be closed instead of deferred. A measured "with vs without" delta will be published here once the integration has been exercised against the replay fixtures.

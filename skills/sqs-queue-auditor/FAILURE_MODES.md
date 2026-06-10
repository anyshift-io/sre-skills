# Failure modes: `sqs-queue-auditor`

This skill is wrong in predictable ways. The list below is the reason it ships with a quality bar that mandates fixture-based replay tests: every failure mode here is a regression vector and gets a test once it shows up in the wild.

## The defining limit: configuration, not behaviour

This skill reads one queue's static attributes. It does not read what the queue is doing. A queue can pass every check in `SKILL.md` and still be dropping messages right now for a reason only the live telemetry shows: a consumer that crashes on a specific payload, a producer that stopped sending, a redrive that is firing constantly. **A clean audit means the configuration is sound, not that the system is healthy.** Every audit says this in its boundary section. Read it as load-bearing, not boilerplate.

## Methodology-level failure modes

### F1. The "is this a processing queue" judgment is supplied, not derived

R1 (no DLQ) only fires when the caller asserts the queue is a processing queue. A pure buffer or fan-out queue with an at-least-once contract enforced elsewhere may legitimately have no dead-letter queue. The audit cannot tell a processing queue from a buffer from the attributes alone; the queue's role is a property of the architecture around it.

**Mitigation in the methodology**: the caller passes `is_processing_queue`. When the role is unknown, the audit should be run as `is_processing_queue=True` (the safe default that surfaces the missing DLQ) and the finding read as "confirm this queue's role" rather than "this is definitely wrong".

**Escalation rule**: if the queue's role is genuinely unknown, surface R1 as a question, not a verdict.

### F2. The R4 age-out estimate is a lower bound, not a guarantee

R4 computes `maxReceiveCount x VisibilityTimeout` as the wall-clock a poison message needs to reach the DLQ, and flags when that exceeds retention. The product is a *lower* bound: it assumes a consumer receives the message roughly once per visibility window. If consumers poll less often, the real time-to-DLQ is longer, which makes the age-out worse, not better. The direction is safe (the flag never under-warns), but the exact margin depends on receive cadence, which is behind the boundary.

**Mitigation in the methodology**: R4 is reported as "poison messages can age out", with the arithmetic shown, so the operator can judge the margin against their actual consumer cadence.

### F3. R3 assumes the DLQ retention is the binding constraint

R3 flags `dlq_retention <= source_retention`. It assumes a message can fail near the end of the source's retention window. If the workload guarantees every message is processed (or fails) within minutes of being sent, a message will never be old enough for the DLQ's shorter retention to bite, and R3 is a false positive in practice. The check is correct for the worst case; the worst case may not occur for a given workload.

**Mitigation in the methodology**: R3 is critical because the worst case is silent total loss of the most diagnostic messages, and the fix (raise DLQ retention to the 14-day max) is cheap and side-effect-free. Prefer the false positive to the silent loss.

### F4. The resource policy is only half the access story

R7 reads the queue's resource `Policy`. The effective set of principals that can `SendMessage` / `ReceiveMessage` is the *union* of that resource policy and every IAM identity policy in the account. A queue with no resource policy at all is not "private": identity policies elsewhere may grant broad access. R7 can only ever flag what the resource policy itself exposes.

**Escalation rule**: a clean R7 is not proof the queue is access-scoped. The IAM-union join is named in every boundary section; closing it needs the account's identity policies, which this skill does not read.

### F5. The low-severity flags cannot be confirmed from the queue

R5 (default visibility), R8 (encryption off), and R9 (FIFO dedup off) each depend on something the queue does not contain: consumer processing time, the data classification, and producer behaviour respectively. They are surfaced as low-severity flags precisely because the skill cannot prove them. Treating a low flag as a confirmed bug is a misread.

## Operational failure modes

### O1. Stale attributes

`GetQueueAttributes` is a point-in-time read. If the queue was reconfigured after the snapshot was taken, the audit describes the old config. `LastModifiedTimestamp` is in the attributes; check it against when the snapshot was pulled.

### O2. The DLQ attributes were not provided

R3 (retention ordering) needs the DLQ's own attributes. When the source queue references a DLQ but the DLQ's `GetQueueAttributes` was not supplied, the retention-ordering check is silently skipped. The audit notes the DLQ is wired but cannot validate its retention.

**Mitigation**: always pull the DLQ's attributes too. Its ARN is in the source queue's `RedrivePolicy.deadLetterTargetArn`.

**Escalation rule**: if R3 could not be evaluated because the DLQ attributes are missing, say so rather than implying the retention ordering is fine.

### O3. Redrive chains and self-references

A DLQ can itself have a `RedrivePolicy` (a chained dead-letter path), and a misconfiguration can point a queue's DLQ at itself. This skill audits one source queue and its immediate DLQ; it does not walk a redrive chain. A multi-hop dead-letter topology needs the cross-resource graph, not a single-queue read.

## When to escalate to a human (summary)

Escalate, or surface as a question rather than a verdict, when **any** of the following is true:

- The queue's role (processing vs buffer) is unknown and R1 fired.
- R3 could not be evaluated because the DLQ attributes were not provided.
- A clean R7 is being read as proof the queue is access-scoped (it is not; the IAM union is unread).
- A low-severity flag (R5, R8, R9) is about to be acted on as a confirmed bug without checking the thing behind the boundary.
- The dead-letter topology is multi-hop (a redrive chain).

Escalation does not mean the agent stops. It means: report the findings, state which checks were deferred and why, name the boundary, and let the human or the next data source close the join.

## How to add a new failure mode here

When a replay test catches a misclassification, or a real-world use surfaces a new pattern, add it under "Methodology-level" or "Operational" with:

1. A short name (`F6`, `O4`, ...).
2. The failure shape, in one sentence.
3. Whatever the methodology already does about it.
4. The escalation rule for it.

Then add a regression test under `tests/` that asserts the audit produces the correct response, even if the response is "defer to the boundary, do not assert a bug".

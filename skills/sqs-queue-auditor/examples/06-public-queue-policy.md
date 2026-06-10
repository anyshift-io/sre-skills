# Worked example 6: open resource policy on an unencrypted queue (R7, R8)

A queue whose resource policy authorises any AWS principal to send to it, with no encryption at rest. The exposure example. Fixtures and replay test under `../fixtures/06-public-queue-policy/` and `../tests/replay_06_public_policy.py`.

## Scenario

- **Queue**: `inbound-webhooks`. Intended to receive events from one specific SNS topic.
- **Symptom**: the resource policy was written to "allow sends" during a hurried integration and never scoped. As written, anyone with an AWS account can push messages onto it.

## Step 1: parse the attributes

```
SqsManagedSseEnabled   false
Policy                 {"Version":"2012-10-17","Statement":[{"Sid":"AllowSend",
                        "Effect":"Allow","Principal":"*","Action":"sqs:SendMessage",
                        "Resource":"...:inbound-webhooks"}]}
RedrivePolicy          {"deadLetterTargetArn":"...:inbound-webhooks-dlq","maxReceiveCount":5}
```

The `Policy` is a JSON string; parsing it gives one `Allow` statement with `Principal: "*"` and **no `Condition`**.

## Step 4: audit exposure

- The statement allows `Principal: "*"` for `sqs:SendMessage` with no narrowing condition (`aws:SourceArn`, `aws:SourceAccount`, `aws:PrincipalOrgID`). That is **R7 (high)**. As written, the policy authorises any AWS principal to send to the queue: the classic confused-deputy and public-queue exposure. A queue that should only accept messages from one SNS topic accepts them from anyone, which means anyone can inject events into the webhook pipeline.
- `SqsManagedSseEnabled` is `false` and there is no `KmsMasterKeyId`, so message bodies are not encrypted at rest. That is **R8 (low)**: low because whether it matters depends on what the webhook payloads contain, which the queue does not tell you.

The contrast that matters: a wildcard principal is not automatically wrong. The standard SNS-to-SQS subscription uses `Principal: "*"` *with* an `aws:SourceArn` condition pinning it to the topic. Example 8 has exactly that pattern and the skill does not flag it. R7 fires on the missing condition, not on the wildcard.

## Steps 2-3, 5: redrive, lifecycle, FIFO

Clean. DLQ present with sane `maxReceiveCount` and good retention (no R1/R2/R3). `5 x 120 = 600s` under retention (no R4). Visibility deliberate at 120s (no R5), retention default (no R6), standard queue.

## Findings

| Code | Severity | Attribute | Fix |
|---|---|---|---|
| R7 | high | `Policy` | Add a `Condition` pinning the principal to the intended source (`aws:SourceArn` for the SNS topic), or name explicit principal ARNs instead of `"*"`. |
| R8 | low | `SqsManagedSseEnabled` / `KmsMasterKeyId` | Enable SQS-managed SSE or a KMS key unless the payloads are confirmed non-sensitive. |

## Boundary

R7 reads the resource policy. That is only half the access story.

- The effective set of principals that can act on this queue is the *union* of this resource policy and every IAM identity policy in the account. A clean resource policy would not prove the queue is private. Join: queue to the account's IAM graph.
- Whether the open policy has actually been used to inject messages is the send metrics by source principal, a time-series. Join: queue to its metrics over time.

## Why this is the R7 / R8 reference

It exercises the precision the check needs: flag the wildcard-with-no-condition, do **not** flag the wildcard-with-`SourceArn` that is the legitimate SNS pattern. And it names the boundary that keeps R7 honest: a resource-policy audit can never be a complete access audit, because identity policies live outside the queue.

# Worked example 8: service wildcard + broad read (W2, W5)

Two wildcards that co-occur and demonstrate the two ends of the severity scale: a sensitive-service wildcard that hands over every secret, and a broad read whose impact the policy genuinely cannot judge. Fixtures and replay test under `../fixtures/08-service-wildcard-exfil/` and `../tests/replay_08_service_wildcard_exfil.py`.

## Scenario

- **Principal**: `role/reporting-exporter`, a reporting job.
- **Symptom**: the job needs to read a couple of secrets and a few buckets. Instead of naming them, the policy grants `secretsmanager:*` and a broad `s3:Get*` — the fast way to make it work.

## Step 1: parse and normalise

Two `Allow` statements:
- `FullSecretsAccess`: `secretsmanager:*` on `Resource: "*"`.
- `ReadAnyBucket`: `s3:GetObject`, `s3:ListBucket` on `Resource: "*"`.

## Step 2: expand the wildcards

`secretsmanager:*` expands to every Secrets Manager action, including `secretsmanager:GetSecretValue` (read any secret), `PutSecretValue` and `DeleteSecret` (tamper), and `CreateSecret`. A reporting job needs `GetSecretValue` on two secrets; the wildcard grants all of it on all of them.

## Step 3: over-broad shapes

- `secretsmanager:*` on a sensitive service is **W2 (high)**: a service-level wildcard on the store of every secret in the account. The expansion shows it includes `GetSecretValue` — the read the job actually wanted — plus the mutating actions it did not.
- `s3:GetObject` / `s3:ListBucket` on `Resource: "*"` is a broad read with no mutating verb, so it is **W5 (low)**, not W4: the principal can read every object in every bucket. Whether that is a breach depends on what those buckets hold — a data-classification question this policy cannot answer. The skill flags it as a reach to verify, **not** a confirmed leak.

The two co-occur and sit at opposite ends of the severity scale, which is the point of the example: the skill rates `secretsmanager:*` high (the service is sensitive by definition) and the broad `s3` read low (the impact is contingent on data it cannot see), rather than flattening both into one "overly broad" verdict.

## Step 4: privilege-escalation combinations

None. No `secretsmanager:*` or `s3` action is a privilege-escalation primitive in the rule set; the findings are the two wildcards.

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| W2 | high | `secretsmanager:*` | Scope to `secretsmanager:GetSecretValue` on the specific secret ARNs the job reads. |
| W5 | low | `s3:GetObject`, `s3:ListBucket` on `Resource: "*"` | Scope to the specific bucket ARNs the job reads. Treat as a flag to verify against data classification, not a confirmed leak. |

## Boundary

- W5's severity is contingent on what data the in-range buckets hold. A bucket of public assets makes it nearly harmless; a bucket of PII makes it critical. That classification is not in the policy. Join: the in-range buckets to their data classification.
- W2 grants `secretsmanager:GetSecretValue` on every secret, but a KMS key policy on a secret's encryption key could still block decryption. Join: the secrets to their KMS key policies.

## Why this is the W2 / W5 reference

It exercises the severity model's honesty in one fixture: a service wildcard the skill *knows* is dangerous (high, asserted) sitting next to a broad read the skill *cannot* judge without data it does not have (low, deferred). A cold agent tends to rate both the same — either both "high, overly permissive" or both shrugged off. The judgment is treating "sensitive by the service's nature" and "sensitive depending on the data" as different severities.

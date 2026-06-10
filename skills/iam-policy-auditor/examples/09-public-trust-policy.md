# Worked example 9: open trust policy on a clean role (X1)

A role whose permissions policy is exemplary and whose trust policy is wide open. The example that shows the skill reads both halves of a role, and the precision that keeps X1 honest. Fixtures and replay test under `../fixtures/09-public-trust-policy/` and `../tests/replay_09_public_trust_policy.py`.

## Scenario

- **Principal**: `role/partner-data-reader`. The permissions policy is scoped to exactly one ingest bucket.
- **Symptom**: during a partner integration, the trust policy was written `Principal: "*"` "to let the partner in", and the intended `sts:ExternalId` condition was never added. As written, any principal in any AWS account can assume the role.

## Step 1: parse and normalise

- Permissions policy: one `Allow` statement, `s3:GetObject` / `s3:ListBucket` on `arn:aws:s3:::partner-ingest-zone` and `/*`.
- Trust policy (`AssumeRolePolicyDocument`): one `Allow` statement, `Principal: "*"`, `Action: sts:AssumeRole`, **no `Condition`**.

## Steps 2–4: the permissions policy

The permissions policy is least-privilege: one service, read-only, scoped to one bucket. No wildcard finding, no privilege-escalation combo. Audited alone, this role is clean.

## Step 5: the trust policy

The trust statement allows `Principal: "*"` to `sts:AssumeRole` with **no narrowing condition** (`aws:PrincipalOrgID`, `aws:SourceAccount`, `sts:ExternalId`). That is **X1 (high)**: any principal in any account can assume `partner-data-reader` and inherit its (scoped, but real) S3 read access. The role's careful permissions policy is irrelevant if anyone on the internet can step into it.

The precision that matters: a wildcard principal is **not** automatically a finding. The standard cross-account vendor pattern is `Principal: "*"` *with* an `sts:ExternalId` (or `aws:PrincipalOrgID`) condition, and the skill must **not** flag that. X1 fires on the *missing condition*, not on the wildcard. This fixture has no condition, so it fires; a narrowed variant would not.

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| X1 | high | trust policy `Principal: "*"`, no condition | Pin the trust to the partner's specific principal ARNs, or add an `sts:ExternalId` condition (the agreed external ID) or an `aws:PrincipalOrgID` condition scoping it to a known org. |

## Boundary

X1 says anyone can assume the role. What they get by doing so is the role's effective permissions.

- The effective access of whoever assumes the role is the union of *all* its identity policies, not just the one bucket read audited here. Join: the role to its full set of attached policies.
- Whether the role has actually been assumed from outside is in CloudTrail `AssumeRole` events, a time-series. Join: the role to its assume history.

## Why this is the X1 reference

It is the example that proves the skill reads a role as two documents, not one: a flawless permissions policy is not a safe role if its trust is open. And it anchors the precision rule — flag `Principal: "*"` only when no condition narrows it — which is the IAM equivalent of the false-positive every cold auditor commits (calling the legitimate scoped-wildcard pattern "public").

# Worked example 11: the clean control (no findings)

A correctly-scoped least-privilege policy. The control case: zero findings, and still a boundary section, because a clean policy is not a clean principal. Fixtures and replay test under `../fixtures/11-clean-least-privilege/` and `../tests/replay_11_clean_least_privilege.py`.

## Scenario

- **Principal**: `role/orders-processor`, a worker that reads one table, writes one bucket prefix, and decrypts with one key.
- **Symptom**: none. This is what a tightened policy looks like, and the example exists to prove the skill does not invent a finding when there is nothing to find.

## Step 1: parse and normalise

Three `Allow` statements:
- `ReadOrdersTable`: `dynamodb:GetItem`, `dynamodb:Query` on one table ARN.
- `WriteProcessedBucket`: `s3:PutObject` on one bucket prefix.
- `DecryptWithOrdersKey`: `kms:Decrypt` on one key ARN, with a `kms:ViaService: dynamodb.eu-west-1.amazonaws.com` condition.

## Steps 2–5: every check, and why each is clean

- **Wildcards (W1–W5)**: no `Action: "*"`, no `NotAction`, no service-level wildcard. Every `Resource` is a specific ARN, not `"*"`, so neither the mutating-write check (W4) nor the broad-read check (W5) fires. `dynamodb:GetItem` and `kms:Decrypt` are sensitive reads, but they are scoped to one table and one key — the opposite of W5's `Resource: "*"`.
- **Privilege-escalation combos (E1–E6)**: the effective allow set contains no `iam:PassRole`, no policy-mutation action, no `lambda:UpdateFunctionCode`, no trust edit, no credential minting. Nothing to combine.
- **Trust (X1)**: no trust policy supplied (and the permissions policy is what was asked about).

**No findings.**

## The boundary still appears

A clean audit is not a silent pass. The report still names what it could not check, because "this policy is sound" is not "this principal is safe":

- The principal's *effective* permissions are the union of every policy attached to it. Only this one was audited; a second attached policy could grant anything. Join: principal to its full set of attached policies.
- A permissions boundary, if any, caps these grants — but also, the *absence* of these findings says nothing about what other policies grant. Join: principal to its permissions boundary.
- An org SCP could Deny even these scoped actions in some accounts. Join: account to its org SCPs.

## Why this is the control

Every auditor's failure mode under test is the urge to find *something*. A cold agent handed a clean policy will often invent a finding ("`kms:Decrypt` is sensitive", "this could be tighter") to look useful. The control fixture asserts the opposite discipline: report zero findings when the policy is correctly scoped, and spend the output on the boundary — the joins that a single clean policy genuinely leaves open — instead of a manufactured concern.

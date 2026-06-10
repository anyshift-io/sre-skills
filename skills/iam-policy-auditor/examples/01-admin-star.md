# Worked example 1: full administrator by wildcard (W1)

The simplest finding and the most common one in the wild: a policy that grants everything, written as a convenience and never tightened. Fixtures and replay test under `../fixtures/01-admin-star/` and `../tests/replay_01_admin_star.py`.

## Scenario

- **Principal**: `role/ci-deployer`, a CI deployment role.
- **Symptom**: the inline policy was written `Action: "*", Resource: "*"` during bootstrap to "just make the pipeline work", and never replaced with the actual permissions the pipeline uses.

## Step 1: parse and normalise

One statement, `Effect: Allow`, `Action: "*"`, `Resource: "*"`.

## Step 2: expand the wildcards

`Action: "*"` expands to every action in AWS. The security-relevant subset alone includes `iam:AttachRolePolicy`, `iam:PassRole`, `iam:CreatePolicyVersion`, `iam:UpdateAssumeRolePolicy`, `lambda:UpdateFunctionCode`, `sts:AssumeRole`, `kms:Decrypt`, `secretsmanager:GetSecretValue` — i.e. every escalation primitive this skill knows about, plus every data-read primitive.

## Step 3: flag the over-broad shapes

`Action: "*"` on `Resource: "*"` is **W1 (critical)**: full administrator by value. The principal can do anything in the account, including rewriting its own and everyone else's permissions.

## Step 4: privilege-escalation combinations

Every E-rule (PassRole+compute, CreatePolicyVersion, UpdateFunctionCode, policy-attach, trust rewrite, credential minting) is satisfied — because admin grants all of them. Listing them individually would be a dozen restatements of the same grant, so the audit **suppresses the E-findings under W1** and reports the one headline.

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| W1 | critical | `Action: "*"` on `Resource: "*"` | Replace the wildcard with the specific actions and resource ARNs the pipeline uses. If admin is genuinely intended, attach the AWS-managed `AdministratorAccess` explicitly (so the intent is auditable) behind a permissions boundary. |

## Boundary

W1 says this policy grants administrator. Whether the principal can *use* it is one join further out.

- A permissions boundary attached to `role/ci-deployer` could cap this to far less. No boundary was supplied; the audit assumes none. Join: principal to its permissions boundary.
- An org SCP could Deny large parts of it. Join: account to its organization's SCPs.

## Why this is the W1 reference

It is the finding everyone can spot and the one that anchors the suppression rule: when a policy is already administrator, the value is *not* enumerating the twelve sub-paths it also satisfies — it is saying "this is administrator, here is the one fix" and pointing at the boundary that is the only thing that might be containing it.

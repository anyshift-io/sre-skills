# Worked example 3: rewrite a managed policy in place (E2)

A single action, buried among routine reads, that lets the principal rewrite the very policy that constrains it. Fixtures and replay test under `../fixtures/03-create-policy-version/` and `../tests/replay_03_create_policy_version.py`.

## Scenario

- **Principal**: `role/pipeline-policy-manager`, which manages a family of pipeline policies.
- **Symptom**: the role legitimately needs to update pipeline policies, so it was granted `iam:CreatePolicyVersion` and `iam:SetDefaultPolicyVersion` on the `pipeline-managed/*` policy path. The grant reads like routine policy administration.

## Step 1: parse and normalise

Two `Allow` statements:
- `ReadDeploymentConfig`: `s3:GetObject` on a specific bucket prefix (correctly scoped — no finding).
- `ManagePipelinePolicies`: `iam:CreatePolicyVersion`, `iam:SetDefaultPolicyVersion`, `iam:GetPolicy`, `iam:ListPolicyVersions` on `arn:aws:iam::...:policy/pipeline-managed/*`.

## Step 2: expand the wildcards

No wildcard Actions. The actions are named; the danger is in what one of them *does*.

## Step 3: over-broad shapes

The s3 read is scoped to a prefix; the IAM statement is scoped to a policy path. Nothing is on `Resource: "*"`. A shape-only review finds nothing.

## Step 4: privilege-escalation combinations

`iam:CreatePolicyVersion` (or `iam:SetDefaultPolicyVersion`) is in the effective allow set. That is **E2 (critical)**: the principal can create a new version of any policy under `pipeline-managed/*` — set as the default version — whose document grants `Action: "*"` on `Resource: "*"`. If any of those managed policies is attached to a more-privileged principal (or to this one), the principal just granted itself administrator.

What makes E2 nasty: it needs no second action, and it changes nothing visible. The policy's name and ARN are unchanged; the attached-policy list looks identical to before; only the *default version's document* is different. A reviewer listing attachments sees the same policy by the same name and moves on.

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| E2 | critical | `iam:CreatePolicyVersion` / `iam:SetDefaultPolicyVersion` | Remove these actions unless this is genuinely a policy-administration role; if it must keep them, scope `Resource` to the exact policy ARNs it manages and confirm none of those policies is attached to a principal more privileged than this one. |

## Boundary

E2 proves the principal can rewrite the `pipeline-managed/*` policies. Whether that yields admin depends on what those policies are attached to.

- A `pipeline-managed` policy attached only to a sandbox role is a smaller E2 than one attached to a deployment role with production access. The attachment graph is not in this document. Join: the policy ARNs to their attachment targets.
- A permissions boundary on this role would cap what any rewritten policy can actually grant *to this role*. Join: principal to its boundary.

## Why this is the E2 reference

E2 is the escalation that survives an attachment audit: the dangerous action is a legitimate-looking policy-management permission, and the exploit leaves every name and ARN intact. The judgment is recognising that "can version a policy" is "can rewrite what that policy grants", and a policy is exactly the thing that grants permissions.

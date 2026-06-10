# Worked example 6: attach an admin policy to a principal (E4)

A permission-management grant, scoped to a role path, that lets the principal make itself an administrator in one API call. Fixtures and replay test under `../fixtures/06-attach-policy-self/` and `../tests/replay_06_attach_policy_self.py`.

## Scenario

- **Principal**: `role/service-onboarding`, which provisions new service roles.
- **Symptom**: onboarding needs to create roles and attach policies to them, so it holds `iam:CreateRole` and `iam:AttachRolePolicy` on the `service/*` role path. Scoping to the path felt like the safe move.

## Step 1: parse and normalise

One `Allow` statement: `iam:AttachRolePolicy`, `iam:CreateRole`, `iam:GetRole`, `iam:ListRolePolicies` on `arn:aws:iam::...:role/service/*`.

## Step 2: expand the wildcards

No wildcard Actions. The danger is in `iam:AttachRolePolicy`, a named action.

## Step 3: over-broad shapes

The statement is scoped to a role path, not `Resource: "*"`. Shape review: clean.

## Step 4: privilege-escalation combinations

`iam:AttachRolePolicy` is in the effective allow set. That is **E4 (critical)**. The principal can attach the AWS-managed `AdministratorAccess` policy to any role under `service/*`. Combined with `iam:CreateRole` on the same path, it can create a brand-new role under `service/*`, attach `AdministratorAccess` to it, and — if it can assume roles in that path (a common trust setup for an onboarding role) — assume the new admin role.

Resource-scoping to `service/*` does **not** prevent the escalation. The scope limits *which* roles can be the target, but the principal controls those roles (it provisions them), so "a role I create under a path I control" is a target it fully owns. The grant statement reads like ordinary permission-management plumbing.

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| E4 | critical | `iam:AttachRolePolicy` | Remove policy-attachment unless this is genuinely an identity-administration role. If it must keep it, attach a **permissions boundary** to every role it creates (so `AdministratorAccess` attached on top is capped to the boundary), and scope the attachable policies with an `iam:PolicyARN` condition to a safe allow-list. |

## Boundary

E4 proves the principal can attach admin to a role it controls. Whether that becomes usable admin is one join out.

- If `service-onboarding` cannot assume the roles it creates, the escalation needs a second principal to use them; whether it can assume them is in its own trust relationships and the created roles' trust policies, not here. Join: principal to the trust graph.
- A permissions boundary on the created roles would cap the attached admin to the boundary. Whether onboarding sets one is a property of its provisioning code, not this policy. Join: principal to the boundary it applies.

## Why this is the E4 reference

E4 is the escalation that resource-scoping appears to fix and does not. The judgment is that scoping `iam:AttachRolePolicy` to a path the principal *controls* is not a real constraint — the principal can populate that path with a target of its choosing. The only real cap is a permissions boundary, which lives outside the policy being audited.

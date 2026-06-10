# Worked example 5: Allow + NotAction (W3)

A statement that reads like a careful, narrow grant and is in fact one of the broadest shapes IAM can express. Fixtures and replay test under `../fixtures/05-not-action-allow/` and `../tests/replay_05_not_action_allow.py`.

## Scenario

- **Principal**: `role/data-platform-operator`.
- **Symptom**: the author wanted "everything except the dangerous services" and reached for `NotAction`, listing the services to keep out. The mental model was a deny-list; the actual effect is an allow-everything.

## Step 1: parse and normalise

One `Allow` statement with **`NotAction`** = `["iam:*", "sts:*", "organizations:*", "account:*", "ec2:*", "lambda:*"]` on `Resource: "*"`.

## Step 2: expand the wildcards

`Allow` + `NotAction` does not mean "allow these few". It means **allow every action in AWS except the ones listed** — every action in every service not named, including every service AWS launches in the future. The expansion is "all of AWS minus six service prefixes", which is thousands of actions across hundreds of services.

## Step 3: over-broad shapes

This is **W3 (high)**. The statement reads narrow (a short list) and grants broad (everything else). `Allow`+`NotAction` is almost always a mistake: the author is thinking in deny-list terms, but `Allow`+`NotAction` auto-grants every action not explicitly excluded, so the grant silently widens every time AWS ships a new service. The safe shapes are `Deny`+`NotAction` (an actual deny-list) or `Allow`+`Action` (an actual allow-list).

Here the exclusion list happens to keep out the escalation-bearing services (`iam`, `sts`, `lambda`, `ec2`), so the privilege-escalation combinations do not fire today. That is luck, not safety: the structural defect is that the grant is open-ended. The day someone needs the role to touch one excluded service and "temporarily" removes it from the list, the shape hands over everything again.

## Step 4: privilege-escalation combinations

None fire — `iam:*`, `sts:*`, `lambda:*`, and `ec2:*` are all excluded, so `iam:PassRole`, `lambda:UpdateFunctionCode`, etc. are not in the effective allow set. The finding is the shape, not a combo.

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| W3 | high | `Effect: Allow` with `NotAction` | Invert to an explicit allow-list: `Effect: Allow` with `Action` naming the permitted actions. Use `NotAction` only with `Effect: Deny`. |

## Boundary

W3 is grounded entirely in the statement shape, so the audit is certain about it. What it cannot see is whether something downstream contains the blast.

- A permissions boundary on this role would cap the open-ended grant to an intersection. None was supplied. Join: principal to its boundary.
- An org SCP could Deny large swathes of the implicitly-allowed services. Join: account to its SCPs.

## Why this is the W3 reference

W3 is the rule that catches an *intent–effect mismatch*. The policy is not over-broad by accident of a wildcard resource; it is over-broad because the author used the one IAM construct that inverts the meaning of the list they wrote. The judgment is recognising `Allow`+`NotAction` on sight as "everything except", regardless of how reassuringly short the exclusion list looks.

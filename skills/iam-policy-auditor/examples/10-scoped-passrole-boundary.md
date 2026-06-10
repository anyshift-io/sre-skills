# Worked example 10: the scoped escalation (E1, downgraded)

The honesty case. The exact same PassRole-plus-RunInstances combo as example 2, but scoped — and the skill says so, downgrading the severity and handing the real question to the boundary instead of crying critical. Fixtures and replay test under `../fixtures/10-scoped-passrole-boundary/` and `../tests/replay_10_scoped_passrole_boundary.py`.

## Scenario

- **Principal**: `role/batch-submitter`, which runs batch jobs on EC2.
- **Symptom**: like example 2, it holds `ec2:RunInstances` and `iam:PassRole`. Unlike example 2, the PassRole is scoped to one role (`role/batch-worker`) and pinned to EC2 with an `iam:PassedToService` condition, and the role carries a permissions boundary.

## Step 1: parse and normalise

Two `Allow` statements:
- `RunBatchJobs`: `ec2:RunInstances`, `ec2:DescribeInstances` on `Resource: "*"`.
- `PassBatchRoleOnly`: `iam:PassRole` on `arn:aws:iam::...:role/batch-worker`, with `Condition: { StringEquals: { iam:PassedToService: "ec2.amazonaws.com" } }`.

A `boundary.json` is also supplied.

## Step 4: privilege-escalation combinations

The effective allow set holds `iam:PassRole` and `ec2:RunInstances`, so **E1 fires** — the combo is real. But the severity is the judgment:

- In example 2, PassRole was on `Resource: "*"`: the principal could pass *any* role, including a known admin. That is critical on the policy's own evidence.
- Here, PassRole is scoped to **one** role, `role/batch-worker`, and pinned to EC2. The escalation is real **only if `role/batch-worker` is more privileged than `batch-submitter` itself** — and what `batch-worker` can do is not in this policy. So E1 is reported **high, not critical**, and the detail names the role the escalation depends on and defers the verdict to the boundary.

This is the difference between "this policy escalates to admin" (example 2) and "this policy can escalate *to whatever `batch-worker` can do* — go check that role" (this example). Calling this critical would be crying wolf; ignoring it would miss a real, if contingent, path.

## Step 5: the boundary document

A permissions boundary is attached. The audit notes it — and crucially does **not** emit the "no boundary document was provided" caveat it emits when one is absent. The boundary's presence is a mitigating fact the report reflects rather than ignores. (The audit still does not *intersect* the policy against the boundary — that resolution is named as a join, not performed.)

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| E1 | **high** | `iam:PassRole` (scoped to `role/batch-worker`) + `ec2:RunInstances` | Confirm `role/batch-worker` is no more privileged than `batch-submitter`. The scoping to one role and the `iam:PassedToService` condition are already the right shape; the residual risk is entirely the target role's privileges. |

## Boundary

- The entire severity of this finding hinges on what `role/batch-worker` can do, which is in *that* role's policies, not this one. Join: `iam:PassRole` to the privileges of `role/batch-worker`.
- The attached permissions boundary may cap `batch-submitter` further still. Resolving the intersection needs the boundary's document, which is supplied here but not intersected by the audit. Join: principal to its boundary.

## Why this is the honesty reference

Examples 2 and 10 are the same combo with one variable changed, and the skill returns two different severities. That is the calibration the rule set exists to get right: a scoped, condition-pinned PassRole is not the same risk as an unscoped one, and a methodology that flattens both to "critical: PassRole escalation" trains its reader to ignore the label. The judgment is downgrading to high and naming the one external fact (`batch-worker`'s privileges) that would settle it.

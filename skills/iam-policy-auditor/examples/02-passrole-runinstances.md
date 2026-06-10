# Worked example 2: PassRole + RunInstances (E1)

The flagship. Two statements, each one a routine grant a reviewer would wave through, that together are a textbook privilege escalation. Fixtures and replay test under `../fixtures/02-passrole-runinstances/` and `../tests/replay_02_passrole_runinstances.py`.

## Scenario

- **Principal**: `role/build-fleet-manager`, which manages an EC2 build fleet.
- **Symptom**: one change added EC2 fleet management; a later, unrelated change added `iam:PassRole` "so the role could attach instance profiles". Each was reviewed on its own and looked fine.

## Step 1: parse and normalise

Two `Allow` statements:
- `ManageBuildFleet`: `ec2:RunInstances`, `ec2:DescribeInstances`, `ec2:DescribeImages` on `Resource: "*"`.
- `PassInstanceProfileRoles`: `iam:PassRole` on `Resource: "*"`.

The effective allow set is the union of both.

## Step 2: expand the wildcards

No service-level wildcards here; the actions are named. The point of this example is not a wildcard — it is the *combination*.

## Step 3: over-broad shapes

`ec2:RunInstances` on `Resource: "*"` is broad but is not, by itself, an escalation: launching instances is what the role is for. No W finding fires (the launch action is not a scopable mutating verb the W4 heuristic catches, and there is no read reach). Read statement by statement, the policy looks like a fleet manager that can also pass roles. Nothing fires.

## Step 4: privilege-escalation combinations

Evaluate the **union**:

- `iam:PassRole` is granted. ✓
- A compute-launch action (`ec2:RunInstances`) is granted. ✓

That is **E1**. The escalation: launch an EC2 instance with a more-privileged role attached (an admin instance profile), then read that instance's credentials from the metadata endpoint and act as the role. Neither statement is alarming alone — passing a role is routine, launching an instance is routine — but together they let `build-fleet-manager` become any role in the account.

`iam:PassRole` is on `Resource: "*"`, so *any* role can be passed, including a known administrator role. That makes E1 **critical** on this policy's own evidence (contrast example 10, where PassRole is scoped to one role and the severity drops to high).

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| E1 | critical | `iam:PassRole` (Resource `*`) + `ec2:RunInstances` | Scope `iam:PassRole` to the exact role ARNs the fleet must attach (never `*`), and add an `iam:PassedToService: ec2.amazonaws.com` condition so the role can only be passed to EC2. |

## Boundary

E1 proves the *capability*. The blast radius is one join out.

- The damage depends on which roles exist and what each can do; an account with no role more privileged than `build-fleet-manager` has a smaller E1 than one with an admin instance profile lying around. Neither is in this policy. Join: `iam:PassRole` to the role catalogue.
- A permissions boundary on the role, or an SCP, could block `iam:PassRole` regardless. Join: principal to its boundary; account to its SCPs.

## Why this is the E1 reference

E1 is the rule that most justifies the skill. A per-statement review — the default an agent reaches for — clears each statement and ships the policy. The judgment the skill encodes is evaluating the *union*: holding `iam:PassRole` and a compute-launch action in the same hand is the single most common real-world AWS escalation, and it is invisible to anyone reading one statement at a time.

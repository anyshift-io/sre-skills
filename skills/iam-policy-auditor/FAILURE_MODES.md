# Failure modes: `iam-policy-auditor`

This skill is wrong in predictable ways. The list below is the reason it ships with a quality bar that mandates fixture-based replay tests: every failure mode here is a regression vector and gets a test once it shows up in the wild.

## The defining limit: one principal's policy, not the account's effective access

This skill reads the policy document(s) attached to one principal. It does not resolve what that principal can *effectively* do, because the effective answer depends on three things that are not in a policy document: the **other** policies attached to the same principal, the **permissions boundary** that caps them, and the **organization SCPs** that can deny them. **A clean audit means the supplied policy is sound, not that the principal is safe — and a critical finding may be capped to nothing by a boundary or SCP the audit never saw.** Every audit says this in its boundary section. Read it as load-bearing, not boilerplate.

## Methodology-level failure modes

### F1. The escalation target's privileges are behind the boundary

E1 (PassRole + compute), E3 (UpdateFunctionCode), and E5 (UpdateAssumeRolePolicy) are escalations *only if* the thing they reach — the role passed, the function's execution role, the role assumed — is more privileged than the principal itself. Those privileges live in other resources the policy does not contain.

**Mitigation in the methodology**: when `iam:PassRole` is scoped to a specific role ARN, E1 is reported **high, not critical**, and the detail names the role the escalation depends on and defers it to the boundary. Only an unscoped (`Resource: "*"`) PassRole — which can pass *any* role, including a known admin — is critical on its own evidence.

**Escalation rule**: a scoped escalation finding is a "verify the target" task, not a proven admin path. Close it by reading the target role/function, which this skill does not do.

### F2. A permissions boundary can cap every Allow

A permissions boundary is the intersection ceiling on a principal: no attached policy can grant beyond it. A policy that reads as full administrator may be capped to read-only by a boundary. This skill reads the boundary only when it is supplied as `boundary.json`; otherwise it assumes none — the louder, safer default.

**Mitigation in the methodology**: the boundary section always names the permissions-boundary join, and explicitly states when no boundary document was provided so the assumption is visible.

**Escalation rule**: before acting on a critical finding, confirm whether a permissions boundary caps it. The finding is "this policy grants X"; whether the principal can *use* X is a boundary question.

### F3. The effective allow set needs every attached policy

The privilege-escalation combos (E1–E6) are evaluated against the *union* of the statements supplied. Their entire value is catching a combo split across statements — but if the two halves live in two *different* attached policies and only one was supplied, the combo is invisible. Conversely, auditing one policy in isolation can miss that a second attached policy already grants the missing half.

**Mitigation in the methodology**: supply *every* managed and inline policy attached to the principal as `policy*.json`; the audit unions them. The boundary names the "full set of attached policies" join and flags when only one document was audited.

### F4. Deny evaluation is approximated

IAM evaluates an explicit `Deny` per concrete resource ARN. This skill treats a `Deny` as effective only when it matches the action on `Resource: "*"` (a blanket deny). A resource-specific `Deny` that would block a specific escalation in practice is not modelled, because the audit does not enumerate the account's ARNs.

**Direction of the error**: the approximation never *under*-reports a grant on a wildcard resource — it can only over-warn when a narrow Deny would have saved the day. Prefer the over-warning to the silent miss; confirm against the real Deny set behind the boundary.

### F5. The wildcard expansion is a curated subset, not all of AWS

Step 2 expands a wildcard to the *security-relevant* concrete actions in this skill's catalogue (the privilege-escalation actions, the credential and key reads). A wildcard also grants thousands of benign actions the catalogue does not name, and AWS adds new actions continually. The expansion is a "here is what matters in this wildcard," not an exhaustive enumeration.

**Mitigation in the methodology**: the boundary names this explicitly. A wildcard finding is grounded in the shape (`svc:*` on a sensitive service), not in the completeness of the expansion list.

### F6. Conditions can neuter a grant the audit reads as open

A statement can carry a `Condition` (an `aws:SourceArn`, an MFA requirement, an IP pin, a `PassedToService`) that makes a broad-looking action safe in practice. The skill reads conditions for the trust-policy narrowing check (X1) and notes a `PassedToService` on PassRole, but it does not fully model arbitrary condition logic on permission statements.

**Escalation rule**: when a flagged statement carries a `Condition`, read it before acting — the grant may already be scoped by something the rule did not evaluate. The trust-policy check (X1) does honour narrowing conditions and must not flag an ExternalId/org-scoped wildcard principal.

## Operational failure modes

### O1. Stale policy snapshot

A policy document is a point-in-time read. If the policy was edited after the snapshot — a new version set as default, a statement added — the audit describes the old policy. For a managed policy, the default version can change without the ARN changing (that is exactly the E2 escalation); confirm the version audited is current.

### O2. The trust policy or boundary was not provided

X1 needs the role's `AssumeRolePolicyDocument`; F2's boundary check needs the permissions boundary. When either is absent, the corresponding check is silently skipped (X1 simply does not fire; the boundary note states no boundary was supplied).

**Escalation rule**: if you need a reachability verdict (X1) or a boundary-capped verdict (F2) and the document was not supplied, say so rather than implying the role is unreachable or uncapped.

### O3. Cross-account and resource-policy grants

This skill audits an *identity* policy (what the principal is allowed to do). The other half of every access decision is the *resource* policy on the target (an S3 bucket policy, a KMS key policy, another account's role trust). A principal with no S3 permission in its identity policy can still read a bucket whose bucket policy grants it. This skill does not read resource policies; that join is the s3-access-auditor's job, not this one.

## When to escalate to a human (summary)

Escalate, or surface as a question rather than a verdict, when **any** of the following is true:

- A critical escalation finding's *target* (the role passed, the function hijacked) has not been read, so its real blast radius is unconfirmed (F1).
- A permissions boundary or org SCP that could cap the finding was not supplied (F2).
- Only some of the principal's attached policies were audited, so the effective allow set is partial (F3).
- A flagged statement carries a `Condition` the rule did not fully evaluate (F6).
- The reachability (trust policy) or boundary document needed for the verdict is missing (O2).

Escalation does not mean the agent stops. It means: report the findings, state which checks were deferred and why, name the boundary, and let the human or the next data source close the join.

## How to add a new failure mode here

When a replay test catches a misclassification, or a real-world use surfaces a new pattern, add it under "Methodology-level" or "Operational" with:

1. A short name (`F7`, `O4`, ...).
2. The failure shape, in one sentence.
3. Whatever the methodology already does about it.
4. The escalation rule for it.

Then add a regression test under `tests/` that asserts the audit produces the correct response, even if the response is "defer to the boundary, do not assert a proven escalation".

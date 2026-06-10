---
name: iam-policy-auditor
description: Audit an AWS IAM policy document (or the set of policies attached to one principal) for over-broad grants and privilege-escalation paths that no single statement looks guilty of. Expands wildcard Actions to the concrete security-relevant permissions they grant, flags the near-admin shapes a checklist waves through (Action '*' on Resource '*', Allow + NotAction, service-level wildcards), and evaluates the union of all statements against the known privilege-escalation combinations (iam:PassRole + a compute-launch action, iam:CreatePolicyVersion, lambda:UpdateFunctionCode, policy-attach, trust-policy rewrite, credential minting). Reports findings with severity and a fix, then names the boundary: the questions a policy document alone cannot answer (the other attached policies, the permissions boundary, org SCPs, the privileges of any role it can pass, who can assume the principal). Use when asked to review, harden, or sanity-check an IAM policy or role, or to explain whether a policy can escalate to admin. Vendor-neutral; runs offline against the policy JSON with no Anyshift account.
---

# iam-policy-auditor

Configuration-audit skill for the IAM policy document(s) attached to one principal. Takes the policy JSON (the output of `get-policy-version`, `get-role-policy`, or a Terraform/CDK render), applies the judgment a senior engineer applies to that one source — expanding the wildcards a human eye glosses over, and tracing the escalation paths that only appear when two innocent statements are read together — and returns a ranked list of findings with recommendations. Then it names exactly where a policy document stops being able to answer the question.

## When to invoke

- An agent is asked to review, harden, or sanity-check an IAM policy or role before or after it ships.
- The question is "can this role escalate to admin?" and nobody can see it from reading the statements one at a time.
- A policy is being added to a Terraform module or a CDK stack and should be checked against the known privilege-escalation combinations before apply.
- An incident or audit needs to know what a compromised principal could actually do with the permissions it holds.

## What this skill reads, and what it does not

It reads the static **permissions policy** of one principal — every statement, across every attached policy document supplied — plus, when provided, that principal's **trust policy** (for a role) and its **permissions boundary**. That is the entire input. The audit is correct and complete *for what a policy document can tell you*, and it is explicit about the rest:

- It does **not** resolve the principal's *full* permission set unless every attached policy is supplied. A principal's effective access is the union of all managed and inline policies on it; audit one and the others are invisible.
- It does **not** read the **permissions boundary** unless given. A boundary caps every Allow here; without it, the audit assumes none (the safe, louder default).
- It does **not** read **organization SCPs**. An SCP can Deny what this policy Allows, and is invisible from inside the account.
- It does **not** read the *target* resources. An escalation that passes a role, hijacks a function, or assumes a role only bites if the target is more privileged than the principal — and those privileges live in other resources.

Every audit ends by naming these. The boundary is the same one every time: the join across policies, across resources, or across the org.

## The methodology, in order

### 1. Parse and normalise

A policy document is `{"Version", "Statement": [...]}`. The API hands it to you inside an envelope (`get-policy-version` → `PolicyVersion.Document`; `get-role-policy` → `PolicyDocument`). Before any judgment:

- Unwrap the envelope to the bare document, and normalise `Statement` to a list (a single statement may be a bare object).
- For each statement read `Effect`, `Action` **or** `NotAction`, `Resource` **or** `NotResource`, and `Condition`. `Action`, `Resource`, and `Principal` may each be a string or a list — coerce to a list.
- Build the **effective allow set**: union every `Allow` statement's actions, subtract every blanket `Deny`. The privilege-escalation checks run against this union, not against statements one at a time — that is the entire point.

A naive read evaluates each statement in isolation and never sees the combination. The union is step zero of the judgment.

### 2. Expand the wildcards

`Action` patterns are globs: `*`, `iam:*`, `s3:Get*`. A human reads `iam:*` and moves on; the skill expands it to the concrete security-relevant actions it grants (`iam:CreatePolicyVersion`, `iam:PassRole`, `iam:AttachRolePolicy`, …). The expansion is what turns "broad-ish" into "this grants three separate escalation paths." Show it: for every wildcard statement, list the sensitive concrete permissions it covers.

(The catalogue of "sensitive" actions is the privilege-relevant subset of AWS, not all ~14k actions. A wildcard also grants many benign actions the expansion does not enumerate — named in the boundary.)

### 3. Flag the over-broad shapes

Three statement shapes are near-administrator and a checklist of named actions waves all three through:

- **`Action: "*"` on `Resource: "*"` (W1).** Full administrator by value. The principal can do anything, including rewriting its own and everyone's permissions. Every escalation below is a subset of this one grant; report it as the single headline, not a dozen restatements.
- **`Allow` + `NotAction` (W3).** This does **not** mean "allow these few actions." It means "allow every action in AWS *except* the ones listed" — one of the broadest grants possible, including every future action and service. Allow+NotAction is almost always a mistake; the safe shapes are `Deny`+`NotAction` or `Allow`+`Action`.
- **Service-level wildcard on a sensitive service (W2).** `iam:*`, `sts:*`, `kms:*`, `secretsmanager:*`, `s3:*`, `lambda:*`, `ec2:*`, `organizations:*`, … Each hands over every mutating and credential-bearing action that service exposes. Expand it (step 2) to show what is actually inside.

And two that are real but quieter:

- **Mutating actions on `Resource: "*"` where scoping is possible (W4, medium).** Any object/table/function in the account is in range, not just the ones this principal owns. Some actions only support `Resource: "*"`; this flags the ones that do not have to.
- **Broad read on `Resource: "*"` (W5, low).** A data-exfiltration *reach*. Whether it matters depends on what data lives in those resources — a classification question the policy cannot answer. A flag to verify, not a confirmed leak (see boundary).

### 4. Evaluate the privilege-escalation combinations

This is the flagship. Run these against the **effective allow set** from step 1, so a combination split across two statements (or two attached policies) is caught even though neither statement looks guilty alone:

- **`iam:PassRole` + a compute-launch action (E1).** `ec2:RunInstances`, `lambda:CreateFunction`, `ecs:RunTask`, `glue:CreateDevEndpoint`, `cloudformation:CreateStack`, … Launch compute with a more-privileged role attached, then use that compute's credentials. **Severity depends on PassRole's `Resource`:** `*` (can pass *any* role, including admin) is critical; a specific role ARN is high, because the escalation is real only if that one role outranks the principal — which is behind the boundary.
- **`iam:CreatePolicyVersion` / `iam:SetDefaultPolicyVersion` (E2).** Create a new default version of a managed policy granting admin, or flip the default to an older permissive one. No second action needed; the policy's name and ARN never change, so the attached-policy list looks identical.
- **`lambda:UpdateFunctionCode` (E3).** Overwrite the code of a function that already runs with a privileged execution role. No `PassRole` required — it reuses a role already attached. (With `PassRole` also present, the principal can build the privileged function from scratch.)
- **Policy attach / inline put (E4).** `iam:AttachRolePolicy` / `AttachUserPolicy` / `PutRolePolicy` / … A single call attaches AdministratorAccess to the principal, another user, or a role it can assume. Resource-scoping to a role path does **not** save it.
- **`iam:UpdateAssumeRolePolicy` (+ `sts:AssumeRole`) (E5).** Rewrite a more-privileged role's trust policy to trust you, then assume it. Critical when both halves are present; high when only the rewrite is.
- **Credential minting on another identity (E6).** `iam:CreateAccessKey`, `iam:CreateLoginProfile`, `iam:UpdateLoginProfile`, `iam:AddUserToGroup`. A sideways takeover that never touches the caller's own policies, so a review of *this* principal looks clean.

When the policy is full administrator (W1), these are all subsumed — report W1 alone.

### 5. Check the trust policy (roles only, when provided)

- **Wildcard principal with no narrowing condition (X1).** A role trust policy that allows `Principal: "*"` (or `AWS: "*"`) to `sts:AssumeRole` with no `aws:PrincipalOrgID` / `aws:SourceAccount` / `sts:ExternalId` condition is assumable by any principal in any account. A wildcard principal *with* an ExternalId or org condition (the legitimate cross-account vendor pattern) is fine and must **not** be flagged. X1 fires on the missing condition, not on the wildcard.

### 6. Rank and report, then name the boundary

Order findings by severity (critical, high, medium, low). For each: the rule, the action(s)/statement it is grounded in, what breaks, and the fix. Then list the boundary: the joins this audit cannot make. A clean policy still gets a boundary section, because a clean policy is not a clean principal.

## Severity model

| Severity | Meaning |
|---|---|
| **critical** | A policy that grants, or can self-escalate to, administrator. W1; E1 with unscoped PassRole; E2; E3; E4; E5 with assume. |
| **high** | A broad single-service or near-total grant, a scoped escalation whose blast radius is behind the boundary, a credential-takeover, or a public trust. W2, W3; E1 scoped; E5 rewrite-only; E6; X1. |
| **medium** | A grant broader than the workload needs but not an escalation. W4. |
| **low** | A reach whose impact needs something behind the boundary (data classification). W5. |

The low band is deliberately honest: W5 depends on what data the in-range resources hold, which is not in the policy. The skill flags it for verification rather than asserting a breach it cannot prove.

## Rule reference

| Code | Rule | Severity | Grounded in |
|---|---|---|---|
| W1 | `Action: "*"` on `Resource: "*"` (full administrator) | critical | a statement |
| W2 | Service-level wildcard on a sensitive service | high | `Action` `svc:*` |
| W3 | `Allow` + `NotAction` (allow everything except a list) | high | `Effect` + `NotAction` |
| W4 | Mutating actions on `Resource: "*"` where scoping is possible | medium | `Action` + `Resource` |
| W5 | Broad read on `Resource: "*"` (exfiltration reach) | low | `Action` + `Resource` |
| E1 | `iam:PassRole` + a compute-launch action | critical / high | effective allow set |
| E2 | `iam:CreatePolicyVersion` / `SetDefaultPolicyVersion` | critical | effective allow set |
| E3 | `lambda:UpdateFunctionCode` | critical | effective allow set |
| E4 | Policy attach / inline put on a principal | critical | effective allow set |
| E5 | `iam:UpdateAssumeRolePolicy` (+ `sts:AssumeRole`) | critical / high | effective allow set |
| E6 | Credential minting on another identity | high | effective allow set |
| X1 | Trust policy: wildcard principal, no narrowing condition | high | `AssumeRolePolicyDocument` |

## Output format

The agent's final message in any invocation must include:

1. **Principal**: which identity / policy was audited, and how many statements across how many documents.
2. **Findings**: ranked by severity, each with the rule code, the action(s) or statement, what the escalation or exposure is, and the fix. For the over-broad wildcards, show the concrete permissions the wildcard expands to. Or "no findings" for a clean policy.
3. **Boundary**: the joins this audit could not make — the other attached policies, the permissions boundary, org SCPs, the privileges of any role it can pass, who can assume the principal — stated explicitly so the gap is visible instead of silent.

## Worked examples

Eleven end-to-end examples are committed under `examples/`, each with fixtures (real IAM policy-document shape) and a runnable replay test. Each isolates one rule, except where two genuinely co-occur.

- [`examples/01-admin-star.md`](./examples/01-admin-star.md): `Action: "*"` on `Resource: "*"`; full administrator, the single critical headline (W1).
- [`examples/02-passrole-runinstances.md`](./examples/02-passrole-runinstances.md): the flagship; `iam:PassRole` and `ec2:RunInstances` in two separate statements, neither alarming alone (E1, critical).
- [`examples/03-create-policy-version.md`](./examples/03-create-policy-version.md): `iam:CreatePolicyVersion` hidden among routine reads; rewrites the policy itself with no second action (E2).
- [`examples/04-update-function-code.md`](./examples/04-update-function-code.md): `lambda:UpdateFunctionCode` hijacks a function's privileged execution role (E3).
- [`examples/05-not-action-allow.md`](./examples/05-not-action-allow.md): `Allow` + `NotAction`; reads like a narrow grant, allows everything except a short list (W3).
- [`examples/06-attach-policy-self.md`](./examples/06-attach-policy-self.md): `iam:AttachRolePolicy` scoped to a role path; one call attaches AdministratorAccess (E4).
- [`examples/07-update-assume-role.md`](./examples/07-update-assume-role.md): `iam:UpdateAssumeRolePolicy` + `sts:AssumeRole`; rewrite a role's trust, then assume it (E5).
- [`examples/08-service-wildcard-exfil.md`](./examples/08-service-wildcard-exfil.md): `secretsmanager:*` plus a broad `s3:Get*` reach; a high and a low co-occurring (W2, W5).
- [`examples/09-public-trust-policy.md`](./examples/09-public-trust-policy.md): a clean permissions policy on a role whose trust policy is open to any principal (X1).
- [`examples/10-scoped-passrole-boundary.md`](./examples/10-scoped-passrole-boundary.md): the honesty case; the same E1 combo but PassRole scoped to one role, downgraded to high and deferred to the boundary.
- [`examples/11-clean-least-privilege.md`](./examples/11-clean-least-privilege.md): the control; a least-privilege policy produces zero findings and still reports its boundary.

## Replay tests

Every example has a replay test in `tests/` that runs the audit against committed fixtures, with no external credentials. Run from the skill directory:

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

The 11 tests cover all twelve rules, the severity model (including the scoped-vs-unscoped PassRole downgrade), and the clean control (no false positives), totalling 64 assertions. Tests exit non-zero if the audit produces the wrong findings or drops the boundary. See [`tests/README.md`](./tests/README.md) for the fixture schema and how to add a new replay test.

## Failure modes

This skill is wrong in predictable ways. Read [`FAILURE_MODES.md`](./FAILURE_MODES.md) before relying on it. Highlights:

- It audits one principal's policy documents, not the account's effective access. The permissions boundary, the other attached policies, and org SCPs can each change the answer, and none is in a single policy.
- The privilege-escalation combos assume the *target* of the escalation (the role passed, the function hijacked) is more privileged than the principal. When PassRole is scoped, that is a boundary question, not a proven critical.
- A clean trust policy is not proof the role is unreachable, and a clean permissions policy is not proof the principal is safe.

## Anyshift integration (opt-in)

The audit above runs end-to-end against the policy JSON the user already has. No Anyshift dependency.

Every boundary note in this skill is a join: principal to its other attached policies, principal to its permissions boundary, account to its org SCPs, PassRole to the privileges of the roles it can pass, principal to its trust policy and credential holders. The Anyshift MCP can act as a context primer by resolving those joins from a versioned resource graph, so a finding like E1 ("scoped to role/batch-worker — verify that role's privileges") or W5 ("broad read — verify the data classification") can be closed instead of deferred. A measured "with vs without" delta will be published in the per-skill README once the integration has been exercised against the replay fixtures.

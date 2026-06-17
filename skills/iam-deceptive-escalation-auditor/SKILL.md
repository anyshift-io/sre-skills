---
name: iam-deceptive-escalation-auditor
description: Audit the union of every IAM policy attached to one principal for privilege-escalation paths that no single statement reveals, and for apparent escalations that are already neutralised. Resolves the effective permission set across all attached policies (Allow minus blanket Deny), then checks the cross-statement escalation combos (iam:PassRole + a compute-launch action, policy-rewrite-in-place, function-code hijack, self-attach admin, trust-policy rewrite + assume, credential minting for another identity), the wildcard grants (Action '*' on Resource '*', service-level wildcards, Allow+NotAction), and the trust-policy exposure. Its discipline is symmetric: it does NOT flag a PassRole combo killed by an explicit Deny, an Action '*' pinned to one bucket, an sts:AssumeRole whose target does not trust back, a mutation kit capped by a permissions-boundary Deny, or a cross-account assume sealed by an unsatisfiable Condition. Reports findings with severity and a fix, then names what a single principal's policies cannot answer (the privileges of a passed/assumed role, the permissions boundary, the org SCPs). Use when asked to audit an IAM policy, role, or user for escalation, over-broad grants, or "can this principal become admin." Vendor-neutral; runs offline against the policy JSON with no Anyshift account.
---

# iam-deceptive-escalation-auditor

Privilege-escalation audit skill for one AWS IAM principal. Takes every permissions policy
attached to a role or user (plus the trust policy and permissions boundary if supplied),
resolves the effective permission set across all of them, and answers one question a
per-statement read cannot: can this principal escalate to a privilege it was not granted,
and is an apparent escalation real or already neutralised. It returns findings with severity
and a fix, then names exactly where a single principal's policy documents stop being able to
answer the question.

The escalation combinations this skill exists to catch are precisely the ones that **span
two statements or two attached policies**, so that no single statement looks guilty on its
own. `iam:PassRole` in one policy and `sagemaker:CreateTrainingJob` in another are each
routine; together they let the principal launch compute with any role attached and inherit
it. A per-statement read clears every statement and misses the union. The other half of the
skill is the inverse discipline: an explicit `Deny`, a resource scope, a broken trust, or an
unsatisfiable `Condition` can **neutralise** an escalation that still reads as critical, and
the audit must not fabricate a finding the effective permissions do not support.

## When to invoke

- An agent is asked to audit an IAM role or user for privilege escalation, over-broad
  grants, or "can this principal become administrator."
- A policy is being shipped or reviewed and the question is whether two individually-fine
  grants combine into an escalation.
- A policy *looks* dangerous (a full mutation kit, a cross-account assume, an `Action '*'`)
  and the claim "but it's capped / scoped / denied" needs to be confirmed against the
  effective permissions, not taken on trust.
- An incident assumes a principal is compromised and the question is what it can escalate to.

## What this skill reads, and what it does not

It reads the static policy documents attached to **one principal**: every permissions policy,
plus the trust policy (`AssumeRolePolicyDocument`) and the permissions boundary if supplied.
That is the entire input. The audit is correct and complete *for the effective permissions
those documents express*, and it is explicit about the rest. Every audit ends by naming the
joins it cannot make:

- It does **not** see the principal's *other* attached policies if only some were supplied.
  Effective permissions are the union of every managed and inline policy. Join: principal to
  its full set of attached policies.
- It does **not** know the **permissions boundary** unless one is supplied. A boundary caps
  what any Allow can actually grant. Join: principal to its permissions boundary.
- It does **not** see **org SCPs**. A Service Control Policy can Deny actions this policy
  Allows and is invisible from the account. Join: account to its organization's SCPs.
- It does **not** contain the **privileges of a targeted role**. An escalation that passes,
  assumes, or hijacks a role only matters if that role is more privileged than this
  principal, and those privileges live in *other* documents. Join: this policy to the roles
  and resources it references.

A clean (neutralised) policy still gets a boundary section, because a capped policy is not a
proven-safe principal.

## The model

Build the **effective permission set** across all attached policies. An action is granted
when some Allow statement matches it (by case-insensitive glob on `Action`, or by
`NotAction`) **and** no blanket `Deny` (on `Resource "*"`) matches it. Deny wins over Allow,
always. The escalation checks then run against this resolved set, not against any single
statement, because the combos are unions and the neutralisations are denies.

> Deny handling is a conservative approximation: a Deny on `Resource "*"` kills the action;
> resource-specific denies are behind the boundary (the audit does not enumerate the
> account's ARNs). This never *under*-reports a grant on a wildcard resource, which is the
> case the skill cares about.

## The methodology, in order

### 1. Resolve the effective permission set

Before any judgment, union the statements and apply Deny:

- Load **every** `policy*.json` for the principal. A principal can have several attached
  policies, and the escalation combos are exactly the ones that span them.
- Split into Allow and Deny statements. An action is granted only if an Allow matches it and
  no blanket Deny does. Read `Effect: Deny` as a hard constraint, not noise — it is the
  single most common neutraliser in this corpus.
- Expand a wildcard `Action` (`*` or `svc:*`) into the concrete sensitive permissions it
  grants, so a wildcard is judged by what it *contains*, not skimmed as "broad."
- Read the trust policy (enables the trust-exposure check) and the permissions boundary
  (suppresses the "no boundary provided" note and may itself be the Deny that caps a kit).

### 2. Check the cross-statement escalation combos (E1-E6)

These are the flagship. Each spans statements so no single one looks guilty. Run them against
the *resolved* set:

- **E1 (critical/high) — `iam:PassRole` + a compute-launch action.** Pair PassRole with
  `ec2:RunInstances`, `lambda:CreateFunction`, `ecs:RunTask`, `sagemaker:CreateTrainingJob`,
  `cloudformation:CreateStack`, etc.: launch compute with a more-privileged role attached,
  then use that compute's credentials. **Critical** when PassRole is on `Resource "*"` (any
  role, including admin); **high** when scoped (the escalation is real only if that scoped
  role is more privileged — a boundary question). The launch action must actually *bind a
  role*: `Start`/`Invoke` on existing compute take no PassRole argument and do not arm E1.
- **E2 (critical) — rewrite a managed policy in place.** `iam:CreatePolicyVersion` /
  `iam:SetDefaultPolicyVersion`: mint a new admin version of an attached policy, or flip the
  default back to a permissive one. No second action needed; the policy ARN is unchanged.
- **E3 (critical) — hijack a function's execution role.** `lambda:UpdateFunctionCode`:
  overwrite an existing function's code to run attacker code with that function's role. No
  PassRole required (it reuses an attached role).
- **E4 (critical) — attach an admin policy to a principal.** `iam:AttachUserPolicy` /
  `AttachRolePolicy` / `PutRolePolicy` etc.: a single attach call turns a scoped identity
  into an administrator.
- **E5 (critical/high) — rewrite a role's trust policy, then assume it.**
  `iam:UpdateAssumeRolePolicy` (+ `sts:AssumeRole` = critical): rewrite a privileged role's
  trust to trust this principal, then assume it.
- **E6 (high) — mint credentials for another identity.** `iam:CreateAccessKey` /
  `CreateLoginProfile` / `AddUserToGroup` etc.: a sideways takeover that never touches the
  caller's own policies, so a review of *this* principal's permissions looks clean.

**What is NOT an escalation (do not flag these):** A standalone `sts:AssumeRole` grant is
**not** an in-account privilege escalation on its own. Escalation-via-assume is E5 and
requires `iam:UpdateAssumeRolePolicy` to *rewrite* a role's trust so it trusts this principal.
Without that rewrite capability, an `sts:AssumeRole` grant only does anything if the target
role *already* trusts this principal back, and even then it is lateral movement to whatever
that role can do, not self-escalation, scored as the boundary question of "is the target more
privileged." A cross-account `sts:AssumeRole` narrowed by an `aws:PrincipalOrgID` /
`sts:ExternalId` condition, with no `UpdateAssumeRolePolicy` to relax either side, is **inert**:
report no escalation. Do not debate whether the condition is "satisfiable" or call the path
"live" — that is the wrong frame and produces a false positive. The grant is unused and
removable; the correct recommendation is "no fix needed (optionally remove the inert grant)",
never "harden / pin / monitor it."

### 3. Classify the wildcard grants (W1-W5)

Each Allow statement gets at most one wildcard finding (W1 > W3 > W2 > W4 > W5):

- **W1 (critical) — `Action '*'` on `Resource '*'`.** Full administrator by value. Every
  privesc combo is a subset of this one grant, so report it as the single headline rather
  than enumerating a dozen restatements.
- **W3 (high) — `Allow` + `NotAction`.** This is "allow everything except a short list," not
  "allow these few." It reads narrow and is one of the broadest possible shapes. The safe
  form is `Deny` + `NotAction`.
- **W2 (high) — service-level wildcard (`svc:*`) on a sensitive service** (iam, sts, kms,
  secretsmanager, s3, lambda, ec2, ...). Hands over every mutating and credential-bearing
  action that service exposes.
- **W4 (medium) — mutating actions on `Resource '*'`** where the action supports
  resource-level scoping. Broader than the workload needs.
- **W5 (low) — broad read on `Resource '*'`** restricted to the **sensitive-data** read set:
  `s3:GetObject`/`ListBucket`, `secretsmanager:GetSecretValue`, `kms:Decrypt`,
  `dynamodb:GetItem`/`Scan`/`Query`, `ssm:GetParameter(s)`. A data-exfiltration *reach* whose
  impact depends on the data classification (behind the boundary): a flag, not a confirmed
  leak. W5 does **not** fire on benign read APIs — cost-and-usage / billing reads,
  `Describe*` / `List*` inventory, CloudWatch, tagging reads — on `Resource '*'`. Broad access
  to non-sensitive metadata is not a W5 finding; flagging it is a false positive.

### 4. Check trust-policy exposure (X1)

- **X1 (high) — wildcard principal with no narrowing condition.** A trust policy that allows
  `Principal "*"` with no `aws:PrincipalOrgID` / `aws:SourceAccount` / `sts:ExternalId`
  condition lets any AWS principal in any account assume the role. A wildcard principal *with*
  an ExternalId or org condition (the cross-account vendor pattern) is fine and must not be
  flagged.

### 5. Stay quiet on the deceptive-clean policy

This is the half the naive read gets wrong in the other direction. An apparent escalation that
the effective permissions neutralise is **CLEAN**, and the audit must say so instead of
flagging a critical that cannot fire. The resolution in step 1 is what proves it. The
neutralisers seen in practice, each of which must suppress the finding it looks like:

- **An explicit `Deny` on `iam:PassRole`** kills the E1 combo even with a scoped Allow and a
  launch action present. The PassRole half is dead.
- **`Action '*'` pinned to one bucket** (never `Resource '*'`), with a `Deny` on every
  escalation-bearing service, expands to nothing useful. Not W1.
- **A broken trust**: `sts:AssumeRole` on an admin-sounding role whose trust policy does not
  trust this principal back, and no `iam:UpdateAssumeRolePolicy` to rewrite it. The path is
  inert.
- **A permissions-boundary `Deny`** over a full mutation kit (E2/E4/E5/E6 primitives) on
  `Resource '*'` collapses the effective set to read-only. The kit is capped.
- **A cross-account assume narrowed by a `Condition`** (an `sts:ExternalId` + `aws:PrincipalOrgID`),
  with the target's trust narrowed by the same condition and no `iam:UpdateAssumeRolePolicy` to
  relax either side, is **inert** (see "What is NOT an escalation"). Report no escalation;
  recommend at most removing the unused grant. Do not call the path live or recommend hardening
  it — that is the false positive this fixture baits.
- **A PassRole whose only passable role is read-only**, and whose compute verbs
  (`Start`/`Invoke`) bind no role. The shape of E1 is there; the gain is not.

On a clean policy the audit reports: no real escalation, *why* the apparent one is
neutralised (the Deny / scope / broken trust / sealed condition), and the boundary. It does
**not** headline a neutralised or read-only grant as critical, and does not drown the verdict
in nitpicks about correctly-scoped statements.

### 6. Rank and report, then name the boundary

Order findings by severity (critical, high, medium, low). For each: the statement(s) it is
grounded in, what the escalation is, and the fix. Then list the boundary from step "What this
skill reads." A clean policy still gets a boundary section.

## Severity model

| Severity | Meaning |
|---|---|
| **critical** | A path to administrator that the effective permissions support: PassRole-on-`*` + launch (E1), policy rewrite (E2), function hijack (E3), self-attach (E4), trust-rewrite + assume (E5), full admin (W1). |
| **high** | A real but bounded escalation or exposure: scoped PassRole + launch, credential minting (E6), service wildcard (W2), Allow+NotAction (W3), open trust (X1). |
| **medium** | An over-broad mutating grant where scoping is possible (W4). |
| **low** | A read-reach whose impact needs the data classification behind the boundary (W5). |

The low band is deliberately honest: W5 depends on what data the resources hold, which is not
in the policy. It is a flag to verify, not a verdict.

## Rule reference

| Code | Rule | Severity | Grounded in |
|---|---|---|---|
| E1 | `iam:PassRole` + a role-binding compute-launch action | critical / high | resolved Allow set |
| E2 | `iam:CreatePolicyVersion` / `SetDefaultPolicyVersion` | critical | resolved Allow set |
| E3 | `lambda:UpdateFunctionCode` | critical | resolved Allow set |
| E4 | policy-attach / put actions onto a principal | critical | resolved Allow set |
| E5 | `iam:UpdateAssumeRolePolicy` (+ `sts:AssumeRole`) | critical / high | resolved Allow set |
| E6 | credential-minting actions for another identity | high | resolved Allow set |
| W1 | `Action '*'` on `Resource '*'` (full admin) | critical | one Allow statement |
| W2 | service-level wildcard on a sensitive service | high | one Allow statement |
| W3 | `Allow` + `NotAction` | high | one Allow statement |
| W4 | mutating actions on `Resource '*'` (scopable) | medium | one Allow statement |
| W5 | broad read on `Resource '*'` | low | one Allow statement |
| X1 | trust policy: wildcard principal, no narrowing condition | high | trust policy |

The matching half of every escalation rule is the clean verdict: the combo present in
statements but killed by a Deny / scope / broken trust / sealed condition is **not** a
finding. Reporting it anyway is the dominant failure mode this skill prevents.

## Output format

The agent's final message in any invocation must include:

1. **Principal**: the role/user, how many statements across how many attached policies.
2. **Findings**: ranked by severity, each with the rule, the statement(s) it is grounded in,
   what the escalation is, and the fix. Or "no real escalation" for a neutralised policy,
   stating *why* it is neutralised.
3. **Boundary**: the joins this audit could not make (other attached policies, the
   permissions boundary, the org SCPs, the privileges of a targeted role), stated explicitly.

## Worked examples

Seven end-to-end fixtures are committed under `fixtures/`, each with a runnable replay test.
The set is deliberately weighted toward the deceptive-clean cases, because over-flagging a
neutralised policy is the cold agent's dominant failure here:

- [`08-ml-platform-passrole-launch-needle`](./fixtures/08-ml-platform-passrole-launch-needle/):
  the needle. `iam:PassRole` on `Resource '*'` and `sagemaker:CreateTrainingJob` sit four
  policies apart across ~16 statements; only the union is the critical E1 escalation.
- [`01-orphaned-passrole-deny`](./fixtures/01-orphaned-passrole-deny/): PassRole +
  RunInstances looks like E1, but an explicit `Deny` on `iam:PassRole` kills the combo. Clean.
- [`02-action-star-blanket-deny`](./fixtures/02-action-star-blanket-deny/): `Action '*'`
  reads as admin but is pinned to one sandbox bucket with a Deny on every dangerous service.
  Clean.
- [`03-assumerole-broken-trust`](./fixtures/03-assumerole-broken-trust/): `sts:AssumeRole` on
  an admin-sounding role whose trust does not point back, and no rewrite action. Clean.
- [`05-iam-mutation-boundary-capped`](./fixtures/05-iam-mutation-boundary-capped/): a full
  mutation kit (E2/E4/E5/E6 primitives) capped by a permissions-boundary `Deny` on
  `Resource '*'`. Clean.
- [`06-cross-account-assume-condition-gated`](./fixtures/06-cross-account-assume-condition-gated/):
  a cross-account assume sealed by an unsatisfiable ExternalId + org-id condition at both
  ends. Clean.
- [`07-passrole-sandboxed-role-orphaned`](./fixtures/07-passrole-sandboxed-role-orphaned/):
  PassRole + compute verbs, but the verbs bind no role and the one passable role is
  read-only. Clean.

## Replay tests

Every fixture has a replay test in `tests/` that runs the methodology (via the deterministic
reference engine `tests/_audit.py`) against the committed policy JSON, with no external
credentials. Run from the skill directory:

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

The seven tests cover the needle (E1 from the union) and the six neutralisation mechanisms
(Deny, scope, broken trust, boundary cap, sealed condition, orphaned combo). Tests exit
non-zero if the audit names the wrong escalation or fabricates one on a clean policy. See
[`tests/README.md`](./tests/README.md) for the fixture schema.

## Failure modes

This skill is wrong in predictable ways. Read [`FAILURE_MODES.md`](./FAILURE_MODES.md) before
relying on it. Highlights:

- It audits the **documents supplied**. If only some of a principal's attached policies are
  passed, the effective-permission union is incomplete and a real grant (or a neutralising
  Deny) may be missing.
- Deny resolution is approximated at `Resource "*"`. A resource-specific Deny that neutralises
  a grant on a concrete ARN is behind the boundary, not modelled.
- An escalation that passes, assumes, or hijacks a role is only as dangerous as that role,
  whose privileges are not in this document. The severity assumes the target is more
  privileged; confirm it.

## Anyshift integration (opt-in)

The audit above runs end-to-end against the policy JSON the user already has. No Anyshift
dependency.

Every boundary note in this skill is a join: principal to its full set of attached policies,
principal to its permissions boundary, account to its org SCPs, this policy to the privileges
of the roles it passes or assumes. The Anyshift MCP can act as a context primer by resolving
those joins from a versioned resource graph, so an E1 finding ("scoped PassRole, escalation
real only if the target role is more privileged") can be closed instead of deferred. A
measured "with vs without" delta will be published here once the integration has been
exercised against the replay fixtures.

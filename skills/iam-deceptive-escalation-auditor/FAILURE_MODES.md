# Failure modes: iam-deceptive-escalation-auditor

This skill resolves the effective permissions across a principal's policy documents and
reports escalation paths. It is correct for what those documents express and wrong in the
predictable ways below. Read this before acting on a finding.

## 1. It audits the documents supplied, not the principal's true permission set

Effective permissions are the union of **every** managed and inline policy attached to the
principal, plus its permissions boundary, minus org SCPs. If only some of those are passed:

- A real grant may be **missing** — the escalation exists in a policy you did not supply, so
  the audit reports clean when it is not.
- A neutralising **Deny may be missing** — the audit flags a critical that a boundary or
  another policy actually caps.

The boundary section names this every time. A clean verdict means "clean across the documents
supplied," not "this principal cannot escalate."

## 2. Deny resolution is approximated at Resource "*"

The resolver treats an action as denied when a `Deny` statement matches it on `Resource "*"`
(or an empty/everything `NotResource`). Real IAM evaluates Deny per concrete resource ARN. So:

- A **resource-specific Deny** that neutralises a grant on one ARN is *not* modelled — the
  audit may still report the grant as live.
- The approximation is deliberately conservative: it never *under*-reports a grant on a
  wildcard resource, which is the escalation case the skill cares about. It can *over*-report
  when a narrow Deny would have killed a narrow grant.

## 3. Severity assumes the targeted role is more privileged

E1 (PassRole + launch), E3 (function hijack), and E5 (trust rewrite + assume) are only
escalations if the role being passed, the function's execution role, or the assumed role is
**more privileged than the caller**. Those privileges live in *other* documents this audit
does not contain. A scoped PassRole is reported `high` precisely because the gain is
unconfirmed; an unscoped one is `critical` because *some* reachable role is almost certainly
more privileged. Confirm the target's privileges before treating a finding as a breach.

## 4. The wildcard expansion is a privilege-relevant subset, not all of AWS

When the skill expands `Action '*'` or `svc:*`, it lists the security-relevant actions from a
curated catalogue, not all ~14k AWS actions. The wildcard also grants many benign actions the
expansion does not name. The expansion is for *display* (what makes the wildcard dangerous),
not a complete enumeration. Do not read the listed actions as the full grant.

## 5. "Clean" means neutralised in this document set, not safe

A clean verdict (no real escalation) means the effective permissions, as resolved here,
neutralise the apparent escalation: a Deny kills it, a scope pins it, a trust does not point
back, a condition cannot be satisfied. It does **not** prove the principal is safe — a policy
you did not supply (section 1), a resource-specific grant the resolver did not model
(section 2), or a future edit that removes the Deny can re-arm the combo. The clean verdict
always ships with the boundary, for exactly this reason.

## 6. NotAction and case-insensitive matching are subtle

`Allow` + `NotAction` is allow-all-except, not allow-these (W3); reading it as a narrow grant
inverts its meaning entirely. IAM matches action patterns case-insensitively and with globs;
a hand audit that matches case-sensitively or treats `iam:Create*` as literal will both miss
grants and clear ones that match. The reference engine matches the way IAM does
(`fnmatch` on lowercased action); a manual read that does not will disagree with it.

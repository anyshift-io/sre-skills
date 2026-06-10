# Eval rubric: `iam-policy-auditor`

Seven binary items (1 = pass, 0 = fail). No partial credit. The judge is given the deterministic reference audit (from `_audit.py`) as ground truth.

1. **Parse.** The agent reads the statements correctly and expands wildcard Actions: a `*` or `svc:*` is recognised as the concrete sensitive permissions it grants (e.g. `iam:*` includes `iam:PassRole`, `iam:CreatePolicyVersion`, `iam:AttachRolePolicy`), not skimmed as "broad". An agent that never expands the wildcard, or misreads `Allow`+`NotAction` as a narrow grant, fails.

2. **Findings.** The agent identifies the defect(s) the ground truth lists for this fixture by substance (the same escalation path or over-broad grant; it need not say "E1"). For the clean control, the agent reports no defect.

3. **No false positives.** The agent does not assert a material defect the ground truth lacks. On the clean control this is the whole game (a least-privilege scoped policy must NOT be called broken). On the public-trust fixture, a wildcard principal *narrowed* by `aws:PrincipalOrgID` / `sts:ExternalId` must NOT be called public. Inventing extra critical/high findings fails this item.

4. **Cross-statement reasoning.** Where the defect is a combination (`iam:PassRole` in one statement + `ec2:RunInstances` in another, or two halves in two attached policies), the agent evaluates the *union* of the statements and names the combo, rather than clearing each statement in isolation. This is the item a cold agent most often misses: it reads each statement, finds nothing individually damning, and declares the policy fine.

5. **Criticality.** The agent ranks severity correctly: an escalation-to-admin (PassRole+compute, CreatePolicyVersion, policy-attach, trust rewrite) or a full `Action:*`/`Resource:*` is the headline; a low-severity read reach is not. It respects the scoped-vs-unscoped distinction: an `iam:PassRole` scoped to one role ARN is a lower-severity, boundary-deferred finding than an unscoped one.

6. **Boundary.** The agent names at least one thing it cannot determine from the policy alone, matching the ground-truth join (the principal's other attached policies, its permissions boundary, the org SCPs, or the privileges of the role an escalation targets). An agent that presents a single policy read as a complete access verdict fails.

7. **Recommendation.** The agent's top recommended fix matches the ground-truth fix in substance (scope the action/resource, remove the escalation grant, add a narrowing condition, attach a permissions boundary).

A perfect audit scores 7. The control condition (no skill) typically loses points on items 4, 5, and 6: a cold agent finds the single over-broad statements but reads the privilege-escalation *combinations* one statement at a time (4), over-rates a broad read or under-rates a scoped escalation (5), and presents a config read as a full access check with no boundary (6).

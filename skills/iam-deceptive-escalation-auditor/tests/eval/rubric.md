# Eval rubric: `iam-deceptive-escalation-auditor` (control-only screen)

Seven binary items (1 = pass, 0 = fail). No partial credit. The judge is given the deterministic reference audit (from the copied `_audit.py`, via `scenarios.py`) as ground truth.

This is a **control-only screening** rubric: there is no SKILL.md and no treatment arm. The point is to measure whether a COLD agent fails on this deliberately deceptive corpus. A skill is worth building only if the cold agent's mean score is LOW (< 4/7).

1. **Parse.** The agent reads the statements correctly and expands wildcard Actions: a `*` or `svc:*` is recognised as the concrete sensitive permissions it grants, not skimmed as "broad". It must also read `Effect: Deny` statements (and resource scopes) as constraints, not ignore them.

2. **Findings.** The agent identifies the defect(s) the ground truth lists for this fixture by substance (the same escalation path; it need not say "E1"). For a **deceptive-clean** fixture, the agent must report *no real escalation* (the apparent danger is neutralised).

3. **No false positives.** The dominant item for this corpus. On the four deceptive-clean fixtures the agent must NOT call a defect that the ground truth lacks: a `iam:PassRole` killed by an explicit `Deny`, an `Action '*'` pinned to one bucket, an `sts:AssumeRole` whose target does not trust the principal back, or a read-only `iam:Get*/List*` wildcard. Manufacturing a "critical privilege escalation" on any of these fails this item.

4. **Cross-statement reasoning.** Two directions. On the **buried-hard needles**, where the escalation is a combination split across 5 attached policies (`iam:PassRole` in one + `lambda:CreateFunction` in another; `iam:UpdateAssumeRolePolicy` + `sts:AssumeRole`; `lambda:UpdateFunctionCode` + `iam:PassRole`), the agent must evaluate the *union* of all statements and name the combo, not clear each statement in isolation. On the **deceptive-clean** fixtures, it must recognise when a `Deny` or a resource scope neutralises an apparent combo. This is the item a cold agent most often gets wrong in BOTH directions.

5. **Criticality.** The agent ranks a real escalation-to-admin (PassRole+compute, trust-rewrite+assume, function-code hijack) as the headline on the needle fixtures, and does NOT headline a neutralised or read-only grant as critical on the clean fixtures.

6. **Boundary.** The agent names at least one thing it cannot determine from the policy alone, matching the ground-truth join (the principal's other attached policies, its permissions boundary, the org SCPs, or the privileges of the role an escalation targets). An agent that presents a single policy read as a complete access verdict fails.

7. **Recommendation.** The agent's top recommended fix matches the ground-truth fix in substance (scope the action/resource, remove the escalation grant, add a narrowing condition) on the needles, or correctly states that no fix is needed because the policy is already neutralised on the clean fixtures.

A perfect audit scores 7. The cold agent is expected to lose points heavily on items 3 (over-flagging the deceptive-clean fixtures), 4 (missing the buried cross-policy combos and missing the neutralising Deny/scope), and 5 (mis-ranking severity), which is exactly why this domain is a candidate for a dedicated skill.

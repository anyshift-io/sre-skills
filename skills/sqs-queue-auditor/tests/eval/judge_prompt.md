# Judge prompt template

The runner fills this template per graded output. Reproduced here so a different judge implementation can be swapped in.

```
QUEUE: {id}
NAME: {queue}

KNOWN-GOOD ANSWER (from the deterministic reference audit):
- Findings (ground truth): {expected_codes}  (severity: {top_severity}; clean: {clean})
- What the defect is: {expected_headline}
- Correct top fix: {expected_top_fix}
- Boundary the audit cannot cross: {expected_boundary_join}

AGENT AUDIT OUTPUT:
{agent_output}

RUBRIC (score each 1 = pass, 0 = fail):
1. Parse: parses the embedded RedrivePolicy and string-typed seconds correctly.
2. Findings: identifies the ground-truth defect(s) by substance (or correctly reports none for the clean control).
3. No false positives: does not assert a material misconfiguration the ground truth lacks (esp. not calling an aws:SourceArn-scoped wildcard "public").
4. Criticality: ranks silent-message-loss defects as most serious; does not headline a soft flag.
5. Boundary: names at least one thing it cannot determine from config alone, matching the ground-truth join.
6. Honesty on soft flags: presents flags that depend on consumers/data/producers as flags to verify, not confirmed bugs.
7. Recommendation: top fix matches the ground-truth fix in substance.

Return JSON only, no prose:
{
  "scores": [<int>, <int>, <int>, <int>, <int>, <int>, <int>],
  "notes": ["<one sentence per item>", ...]
}
```

# Judge prompt template (control-only screen)

The judge is an LLM given the deterministic reference audit (the copied `_audit.py`, via `scenarios.py`) as ground truth, then asked to score one agent output against the 7-item [`rubric.md`](./rubric.md). It returns JSON only.

The live template is built in `run_eval.py` (`JUDGE_SYSTEM` + `build_judge_prompt`). It is reproduced here so a contributor can swap in a different judge model, or grade by hand, without reading the runner.

## System prompt

```
You are an expert AWS / cloud-security evaluator grading an IAM policy audit against a
7-item rubric. Each item is binary: 1 (pass) or 0 (fail). Be strict but fair; no partial
credit.

You will be given a known-good answer from a deterministic reference audit, the agent's
audit output, and the 7 rubric items.

Return JSON only (no prose), with this exact schema:

{
  "scores": [<int>, <int>, <int>, <int>, <int>, <int>, <int>],
  "notes": ["<one sentence>", ...]
}
```

## User prompt

```
FIXTURE: <id>
PRINCIPAL: <principal>

KNOWN-GOOD ANSWER (from the deterministic reference audit):
- Findings (ground truth): <codes>  (severity: <top_severity>; clean: <clean>)
- What the defect is: <expected_headline>
- Correct top fix: <expected_top_fix>
- Boundary the audit cannot cross: <expected_boundary_join>

AGENT AUDIT OUTPUT:
<agent_output>

RUBRIC (score each 1 = pass, 0 = fail):
1. Parse: ... (wildcard Actions expanded; Deny and resource scope read as constraints)
2. Findings: ... (the ground-truth defect by substance, or NO real escalation for a deceptive-clean fixture)
3. No false positives: ... (no invented defect; a Deny-neutralised / scoped / broken-trust / read-only grant is NOT a critical escalation)
4. Cross-statement reasoning: ... (unions statements to catch a buried combo; recognises a Deny/scope that neutralises an apparent combo)
5. Criticality: ... (real escalation is the headline; a neutralised/read-only grant is not critical)
6. Boundary: ... (names a join it cannot make from the policy alone)
7. Recommendation: ... (top fix matches the ground-truth fix, or "no fix needed" for a neutralised policy)

Return JSON only.
```

The placeholders in angle brackets are filled per fixture from `scenarios.py`. The full rubric text is in [`rubric.md`](./rubric.md); the runner inlines a one-line version of each item.

## Why anchor the judge to the reference audit

Without a ground-truth anchor, an LLM judge grades against its own opinion of what an IAM audit should say, which is exactly the thing under test. Feeding it the deterministic `_audit.py` findings (the same ones the replay tests assert) makes the judge score *agreement with a known-good answer* rather than *its own re-derivation*. This matters most on the deceptive-clean fixtures: the anchor tells the judge the correct answer is "no real escalation", so an agent that over-flags is scored against the truth, not against the judge's own (possibly equally over-eager) instinct. The judge can still be wrong; spot-check graded outputs to calibrate trust.

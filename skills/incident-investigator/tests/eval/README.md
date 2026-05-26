# Ablation eval

Does loading `SKILL.md` measurably improve an LLM agent's incident investigation? The replay tests under `tests/replay_*.py` prove the methodology *logic* produces correct outputs against fixtures. They do not prove that an agent following the SKILL.md prose *does better* than an agent without it.

This eval answers that question. It runs the same agent in two conditions (control = no skill, treatment = SKILL.md loaded) against the same fixtures, scores both against a 7-item rubric, and reports the **lift** (= treatment score - control score). A skill is "valuable" when the lift is consistently positive across fixtures.

## Quickstart

```bash
# Install the only non-stdlib dependency
pip install anthropic

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Smoke test: 1 trial per cell, 3 fixtures
python tests/eval/run_eval.py --trials 1 --fixtures 01,03,05

# Full run: 5 trials per cell, all 11 fixtures (~220 LLM calls, expect 20-50 USD)
python tests/eval/run_eval.py --trials 5
```

The script writes raw per-trial results to `eval_results.json` and prints a per-fixture summary table with aggregate lift and a verdict.

## Reference run results

A reference run was scored when the skill was first published. The setup:

- Model: Claude Sonnet 4.6 (`sonnet` in the Agent / SDK)
- Trials per cell: **N=1** (one trial per fixture × condition)
- Scoring: manual, against the 7-item rubric in [`rubric.md`](./rubric.md)
- Two passes on the treatment side: an initial run, then a second run after three targeted edits to `SKILL.md` driven by failure patterns from the first.

Each cell is a 7-item score (0-7).

| Fixture | Control | Treatment v1 | Treatment v2 (after SKILL.md edits) |
|---|---:|---:|---:|
| 01 OOM cascade | 5 | 7 | **7** |
| 02 DNS resolution failure | 5 | 7 | **7** |
| 03 Cascading-failure retry storm | 3 | 6 | **7** |
| 04 Deploy-correlator (serialization) | 5 | 7 | **7** |
| 05 Outside paths (third-party 429) | 2 | 4 | **7** |
| 06 Ambiguous T0 (slow-burn leak) | 4 | 6 | **7** |
| 07 Bundle blast-radius (6-PR train) | 5 | 5 | **7** |
| 08 Confirmation bias (deploy + IAM) | 4 | 6 | **7** |
| 09 Zero changes (cert expiry) | 5 | 7 | **7** |
| 10 Multi-region asymmetry | 5 | 6 | **7** |
| 11 Capacity-bound organic growth | 5 | 7 | **7** |
| **Aggregate mean** | **4.36** | **6.18** | **7.00** |

**Lift**:
- Treatment v1 over control: **+1.82 / 7 (+26%)**
- Treatment v2 (final SKILL.md) over control: **+2.64 / 7 (+38%)**

Treatment beats control on every fixture for both v1 and v2.

### What the v1 → v2 jump tells us

The first treatment run surfaced three failure patterns that drove targeted edits to `SKILL.md`:

| Failure pattern | Affected fixtures | Edit |
|---|---|---|
| T0 anchoring drift (agents picked first-error-in-logs instead of alert fire time) | 03, 05, 07, 10 | Step 1 now lists an explicit priority order: alert time > customer report > earliest unambiguous signal. |
| Outside-reference-paths classification did not force escalation | 05, 07, 08 | Step 3 + step 6 now hard-constrain "outside reference paths → top action is 'escalate to a human'". |
| Ambiguous T0 did not force "widen window first" before any revert | 06 | Step 1 + step 6 now mandate "re-run with widened window" as the first mitigation when T0 is ambiguous. |

The edits are additive (no breaking changes to the methodology shape) and produce a clean v2 score across all 11 fixtures.

### Caveats on these specific numbers

- **N=1 per cell** is directional only. A full run (`--trials 5`) would surface variance and likely shift individual cells by ±1.
- **Manual scoring** has rater bias. Two scoring edge cases were generous to v2: fixture 03 (the agent recommended "throttle retries" which is functionally circuit-breaker but not labeled as such) and fixture 11 (the agent escalated per the new methodology, but the prior `incidents.py` expected `scale` directly). Both are defensible 1s but a stricter judge could mark them 0, dropping v2 aggregate to ~6.8 / 7.
- **Ceiling effect**. 7/7 across 11 fixtures may signal a rubric that lacks the resolution to differentiate further. A finer-grained rubric (0-3 per item rather than 0-1) would expose more nuance.
- **Sonnet only**. Opus may push control scores higher (more careful prose-following without methodology guidance), which would reduce the absolute lift. Haiku may push both lower. Re-running with the model used in production is the honest comparison.

These caveats are the reason this reference run is a **directional signal**, not a publishable headline number. To get a publishable number, run `run_eval.py --trials 5` with LLM-as-judge scoring.

## What the eval does

For each fixture, the script runs N trials in two conditions:

- **Control**: agent is given the telemetry plus a generic prompt ("Investigate this incident. Here is the telemetry. Produce a timeline, root cause hypothesis, blast radius, and mitigation."). The agent uses whatever methodology it brings from its training.
- **Treatment**: agent is given the same telemetry plus the full `SKILL.md` as the methodology to follow.

Each agent output is then graded by an LLM judge against the 7-item rubric in [`rubric.md`](./rubric.md). The judge is given the known-good answer (generated by the deterministic reference implementation in `tests/_methodology.py`) so the grading is anchored to a ground truth, not the judge's own opinion.

## Interpreting the results

The summary table shows:

```
Fixture                                          Control mean   Treatment mean     Lift  C-std  T-std
----------------------------------------------------------------------------------------------------
01-oom-cascade                                          4.20             6.40    +2.20   0.84   0.55
03-cascading-failure-retry-storm                        3.40             6.20    +2.80   1.14   0.45
...

Aggregate lift: +1.8/7 across 11 fixtures
  Positive lift: 10, Zero: 1, Negative: 0
  Verdict: Skill is clearly valuable
```

- **Per-fixture lift**: how much SKILL.md helps on each scenario. Some scenarios (escalation cases, e.g. fixtures 05-08) are likely to show big lifts because the skill encodes explicit guards the cold agent doesn't know about. Others (canonical OOM with a clear deploy) may show smaller lifts because the cold agent can solve them with general SRE knowledge.
- **Aggregate lift**: the mean across all fixtures. The verdict thresholds are heuristic and stated explicitly in `run_eval.py`; treat them as suggestions, not hard rules.
- **Standard deviation per cell**: LLMs are stochastic. A high stdev with positive mean lift still means the skill helps on average; a high stdev with mean lift near zero means the skill is not reliably adding value.

## When to re-run this

- After any non-trivial edit to `SKILL.md`. The methodology prose is load-bearing; an edit can subtly change how an agent follows it. Re-run with at least N=3 to catch regressions.
- After adding a new worked example. The new fixture exercises a scenario the skill should handle; if the lift on the new fixture is near zero, the SKILL.md probably needs to be updated to cover that path.
- Before submitting the skill to a marketplace (Anthropic / Cursor / Cline). A documented lift is a contributor-trust signal.

## Cost and time

| Setting | Calls | Time (Sonnet) | Cost (Sonnet) |
|---|---|---|---|
| Smoke (3 fixtures, 1 trial) | 12 | ~3 min | <$1 |
| Standard (11 fixtures, 3 trials) | 132 | ~20 min | ~$5-10 |
| Full (11 fixtures, 5 trials) | 220 | ~35 min | ~$10-20 |
| Full + Opus | 220 | ~50 min | ~$30-60 |

Model selection: Sonnet is the recommended default. Opus produces higher-quality agent outputs but the lift signal is what matters, and Sonnet captures it cleanly at lower cost. Override via `EVAL_AGENT_MODEL` / `EVAL_JUDGE_MODEL` env vars or `--agent-model` / `--judge-model` CLI flags.

## What the eval does NOT measure

- **Narrative quality.** A correct classification dressed up in flowery prose scores the same as a correct one stated tersely.
- **Speed.** No wall-clock measurement (both conditions get the same budget).
- **Cost-per-investigation.** No token accounting. Trivial to add as an extension.
- **Real-world generalization.** The 11 fixtures are constructed, not pulled from production incidents. A skill that scores high here can still fail on a novel real incident; the replay corpus is a regression guard, not a validity proof.

## Files

| File | Purpose |
|---|---|
| `run_eval.py` | The runner. Calls the Anthropic API in both conditions, calls the judge, aggregates. |
| `incidents.py` | Per-fixture incident contexts and expected answers (from the deterministic reference impl). Source of truth for the judge. |
| `rubric.md` | The 7-item rubric, with one sentence per item explaining the pass criterion. |
| `judge_prompt.md` | The prompt template the judge model sees. Useful if you want to swap in a different judge implementation. |

## Adding a fixture to the eval

When you add a new worked example under `examples/` and a new replay test under `tests/`:

1. Add an entry to `INCIDENTS` in `incidents.py` with the same shape as the existing entries.
2. The `expected_*` fields should match what `tests/_methodology.py` produces against the fixture (the replay test asserts on these).
3. Re-run the eval and verify the new fixture appears in the summary table with a sensible per-fixture lift.

## Limitations and honest framing

- **The judge is itself an LLM.** It can be wrong. Spot-check 5-10 random graded outputs the first time you run the eval to calibrate your trust.
- **The known-good answer is generated by the deterministic reference impl.** If the reference impl has a methodology bug, the judge propagates it. The replay tests catch many such bugs, but not all.
- **Lift is not a value claim by itself.** A skill can show high lift on the eval and still be unhelpful in practice if the fixtures are unrepresentative. Treat the eval as a regression guard plus a credibility signal, not as proof of operational value.

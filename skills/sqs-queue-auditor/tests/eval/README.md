# Ablation eval

Does loading `SKILL.md` measurably improve an LLM agent's SQS audit? The replay tests under `tests/replay_*.py` prove the methodology *logic* produces correct findings against fixtures. They do not prove that an agent following the SKILL.md prose *does better* than an agent without it.

This eval answers that question. It runs the same agent in two conditions (control = no skill, treatment = SKILL.md loaded) against the same `GetQueueAttributes` fixtures, scores both against a 7-item rubric ([`rubric.md`](./rubric.md)), and reports the **lift** (= treatment score - control score). A skill is "valuable" when the lift is consistently positive across fixtures.

## Quickstart

```bash
# Install the only non-stdlib dependency
pip install anthropic

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Smoke test: 1 trial per cell, 3 fixtures
python tests/eval/run_eval.py --trials 1 --fixtures 02,04,08

# Full run: 5 trials per cell, all 8 fixtures (~160 LLM calls, expect 10-30 USD)
python tests/eval/run_eval.py --trials 5
```

The script writes raw per-trial results to `eval_results.json` and prints a per-fixture summary table with aggregate lift and a verdict. `python tests/eval/queues.py` prints the deterministic ground-truth findings for every fixture with no API key required.

### Resumable runs

Every `(fixture, condition, trial)` cell is written to `--output` the moment it completes (atomic temp + rename), and on start the runner loads whatever is already there and skips the cells it finds. A crash, a rate-limit, or a Ctrl-C loses at most the one in-flight cell. To finish an interrupted run, **re-run the exact same command**: it fills only the gaps and reprints the full summary.

```bash
python tests/eval/run_eval.py --trials 5            # crashes after 60 of 80 cells
python tests/eval/run_eval.py --trials 5            # runs only the missing 20
python tests/eval/run_eval.py --trials 5 --force    # ignore prior results, re-run all 80
```

A cell whose agent or judge call raises is not recorded, so it is retried on the next run rather than poisoning the file. Keep `--trials` and `--fixtures` identical across resumes, since the cell identity is `(fixture, condition, trial)`.

## Reference run results

The committed reference run (`eval_results.json`). The setup:

- Model: Claude Sonnet 4.6 (`sonnet`)
- Trials per cell: **N=3**
- Fixtures: the four most diagnostic (02 R3, 04 R4, 05 R5/R6, 08 clean control), each run in both conditions
- Scoring: LLM-as-judge against the 7-item rubric, anchored to the deterministic reference audit (`_audit.py`) as ground truth

Each cell is the mean of three 7-item scores (0-7).

| Fixture | Control (N=3) | Treatment (N=3) | Lift |
|---|---:|---:|---:|
| 02 DLQ retention < source (R3) | 5.33 | 7.00 | +1.67 |
| 04 Poison ages out (R4) | 5.33 | 7.00 | +1.67 |
| 05 Default visibility + short retention (R5/R6) | 3.67 | 7.00 | +3.33 |
| 08 Clean control | 1.33 | 7.00 | +5.67 |
| **Aggregate mean** | **3.92** | **7.00** | **+3.08** |

**Lift: +3.08 / 7 (+44%).** Treatment beats control on all four fixtures (4 positive, 0 zero, 0 negative) and sweeps **7.00 / 7 on every fixture with zero variance** (treatment stdev 0.00 across all cells). Verdict: skill is clearly valuable.

### Where the lift comes from

The per-item breakdown is more informative than the totals:

| Rubric item | What control did | What the skill fixed |
|---|---|---|
| 5. Boundary | **0 of 4** control outputs produced a boundary section. Every cold agent presented a config read as a complete health verdict. | Every treatment output named the consumer / IAM-union / metrics-over-time joins it could not cross. |
| 3. No false positives | On the clean control (08), the cold agent flagged the `aws:SourceArn`-scoped wildcard policy as a HIGH "public queue" (the textbook false positive) and invented a "maxReceiveCount=5 too low" finding. | Treatment returned zero findings and explicitly recognised the narrowed wildcard as the legitimate SNS-to-SQS pattern. |
| 4. Criticality | On 05, control rated 5-minute retention CRITICAL and the 30s default visibility HIGH. | Treatment graded them medium / low. |
| 6. Honesty on soft flags | Control asserted the 30s visibility timeout as an "almost always wrong" HIGH defect. | Treatment presented it as a flag deferred to consumer processing time. |

The clean control (08) shows the largest single lift (+6). That is expected: a cold agent's instinct is to find something, and an unconditioned wildcard principal is the most tempting false positive in the corpus. The skill's value there is teaching the agent when *not* to fire.

### A regression the eval caught, then closed

An earlier scoring pass (N=1) did **not** sweep 7/7: on fixture 05, treatment scored 5/7 because it **over-fired R4 as critical**, reasoning that "under load, wall-clock could push a message past the 300s retention" even though the configured-value arithmetic (`5 x 30 = 150s < 300s`) says R4 does not fire. That cost the no-false-positives and criticality items.

This is exactly the kind of failure pattern the eval exists to surface. It drove one targeted edit to `SKILL.md`:

| Failure pattern | Affected fixture | Edit |
|---|---|---|
| R4 raised speculatively on "under load" reasoning rather than the configured-value inequality | 05 | R4 step now states: fire **only** when `maxReceiveCount x VisibilityTimeout > MessageRetentionPeriod` on the configured values; the product is already a lower bound, and queue depth / receive cadence are behind the boundary, not inputs to the check. |

The N=3 reference run above is **after** this edit, and the regression is closed: fixture 05 treatment now scores 7.00/7 across all three trials. The R4 over-fire does not recur.

### Caveats on these specific numbers

- **N=3 per cell** surfaces variance but is still a small sample. Treatment stdev is 0.00 on every cell (stable); control varies by up to ~1.15, so individual control cells may shift +/-1 on a re-run.
- **Four fixtures, not eight.** The reference run used the four most diagnostic fixtures to keep cost down. The committed harness runs all eight; the omitted four (01 R1, 03 R2, 06 R7/R8, 07 R9) are single-finding cases where the cold agent does comparatively well, so including them would *raise* the control mean and *shrink* the headline lift. The four-fixture number is the harder comparison, not the flattering one.
- **LLM-as-judge.** The judge is itself a model and can be wrong. Spot-check graded outputs to calibrate trust.
- **Sonnet only.** Opus may push control scores higher (more careful reasoning without guidance), reducing the absolute lift. Re-run with the production model for the honest comparison.

## What the eval does

For each fixture, the script runs N trials in two conditions:

- **Control**: the agent is given the raw `GetQueueAttributes` JSON (source queue + DLQ) and a generic "audit this SQS queue for misconfigurations" prompt. It uses whatever it brings from training.
- **Treatment**: the agent is given the same JSON plus the full `SKILL.md` as the methodology to follow.

Each output is graded by an LLM judge against the 7-item rubric. The judge is given the deterministic reference audit (`_audit.py`, via `queues.py`) as ground truth, so grading is anchored to a known-good answer rather than the judge's own opinion.

## Files

| File | Purpose |
|---|---|
| `run_eval.py` | The runner. Calls the API in both conditions, calls the judge, aggregates. Needs `ANTHROPIC_API_KEY`. |
| `queues.py` | Per-fixture contexts and ground-truth findings (computed by importing `_audit.py`, so they never drift). Runs offline. |
| `rubric.md` | The 7-item rubric, one sentence per item. |
| `judge_prompt.md` | The judge prompt template, for swapping in a different judge. |

## When to re-run this

- After any non-trivial edit to `SKILL.md`. The prose is load-bearing; re-run with at least N=3 to catch regressions.
- After adding a worked example. If the lift on the new fixture is near zero, `SKILL.md` probably needs to cover that case.
- Before submitting the skill to a marketplace. A documented lift is a contributor-trust signal.

## What the eval does NOT measure

- **Narrative quality.** A correct finding stated tersely scores the same as one dressed up.
- **Speed / cost.** No wall-clock or token accounting (both conditions get the same budget).
- **Real-world generalization.** The eight fixtures are constructed, not pulled from production. High lift here is a regression guard plus a credibility signal, not proof of operational value.

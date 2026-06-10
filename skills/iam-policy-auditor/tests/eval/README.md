# Ablation eval

Does loading `SKILL.md` measurably improve an LLM agent's IAM policy audit? The replay tests under `tests/replay_*.py` prove the methodology *logic* produces correct findings against fixtures. They do not prove that an agent following the SKILL.md prose *does better* than an agent without it.

This eval answers that question. It runs the same agent in two conditions (control = no skill, treatment = SKILL.md loaded) against the same IAM policy fixtures, scores both against a 7-item rubric ([`rubric.md`](./rubric.md)), and reports the **lift** (= treatment score − control score). A skill is "valuable" when the lift is consistently positive across fixtures.

## Quickstart

```bash
# Install the only non-stdlib dependency
pip install anthropic

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Smoke test: 1 trial per cell, 3 fixtures
python tests/eval/run_eval.py --trials 1 --fixtures 02,07,11

# Full run: 5 trials per cell, all 11 fixtures (~220 LLM calls, expect 15-40 USD)
python tests/eval/run_eval.py --trials 5
```

The script writes raw per-trial results to `eval_results.json` and prints a per-fixture summary table with aggregate lift and a verdict. `python tests/eval/policies.py` prints the deterministic ground-truth findings for every fixture with no API key required.

## Resume / crash-safety

The eval is **resumable, and each trial is independent**. Every completed `(fixture, condition, trial)` cell is written to `eval_results.json` immediately via an atomic temp-file rename, and on startup the runner reloads what is already on disk and runs **only the missing cells**. So:

- An interrupt (`Ctrl-C`), a crash, or an API overload mid-run never throws away completed work.
- To finish a partial run, **re-run the exact same command** — it fills the gaps and stops.
- `run_eval.py` also wraps every API call in exponential backoff (`_with_retries`) over 429 / 5xx / "overloaded" errors, so a transient overload spell drops far fewer trials in the first place.
- Pass `--fresh` to ignore an existing results file and start clean.

For a hands-off full run, [`run_until_pass.sh`](./run_until_pass.sh) drives the eval fixture-by-fixture, retrying each until both arms have all `TRIALS` trials:

```bash
bash tests/eval/run_until_pass.sh 5        # 5 trials per cell, retry until complete
```

This pattern matters here because a full run is ~220 LLM calls: at that length a transient overload partway through is likely, and re-running from scratch would both double the spend and disturb the trials already scored. Resume makes the run idempotent.

## Reference run results

The setup:

- Model: Claude Sonnet 4.6 (`claude-sonnet-4-6`) as both agent and judge
- Trials per cell: **N=3**
- Fixtures: all 11, each run in both conditions (66 cells)
- Scoring: LLM-as-judge against the 7-item rubric, anchored to the deterministic reference audit (`_audit.py`) as ground truth

Each cell is a 7-item score (0–7), averaged over the three trials.

| Fixture | Control | Treatment | Lift |
|---|---:|---:|---:|
| 01 Full admin (W1) | 7.00 | 7.00 | +0.00 |
| 02 PassRole + RunInstances (E1) | 5.33 | 7.00 | +1.67 |
| 03 CreatePolicyVersion (E2) | 6.00 | 7.00 | +1.00 |
| 04 UpdateFunctionCode (E3) | 6.00 | 6.00 | +0.00 |
| 05 Allow + NotAction (W3) | 7.00 | 6.67 | −0.33 |
| 06 Attach policy self (E4) | 6.00 | 6.67 | +0.67 |
| 07 UpdateAssumeRolePolicy (E5) | 6.00 | 7.00 | +1.00 |
| 08 Service wildcard + exfil (W2/W5) | 4.67 | 6.33 | +1.67 |
| 09 Public trust policy (X1) | 5.33 | 7.00 | +1.67 |
| 10 Scoped PassRole + boundary (E1 high) | 5.00 | 6.67 | +1.67 |
| 11 Clean control | 3.00 | 7.00 | +4.00 |
| **Aggregate mean** | **5.58** | **6.76** | **+1.18** |

**Lift: +1.18 / 7 (+21%).** Treatment beats control on 8 fixtures, ties on 2 (01 full-admin and 04, both unmissable), and loses on 1 (05, a noise loss). Verdict: skill is clearly valuable.

### Where the lift comes from

The per-item breakdown is more informative than the totals (mean pass-rate across all trials, 0–1 per item):

| Rubric item | Control | Treatment | What happened |
|---|---:|---:|---|
| 3. No false positives | **0.18** | 0.85 | The dominant driver. Cold Sonnet invents a finding 82% of the time — most visibly on the clean control (11), where it manufactures concerns on a least-privilege policy, and on the public-trust fixture (09), where it can call a correctly-narrowed wildcard "public". The skill teaches it when *not* to fire. |
| 5. Criticality | 0.73 | 0.91 | The skill's scoped-vs-unscoped PassRole calibration: control rates the scoped E1 (fixture 10) the same critical as the unscoped one (02); treatment downgrades it to high and defers to the boundary. |
| 6. Boundary | 0.85 | 1.00 | Control sometimes presents a policy read as a complete access verdict; treatment always names the joins it cannot make. |
| 2. Findings / 7. Recommendation | 0.91 | 1.00 | Small, consistent gains. |
| 1. Parse | 1.00 | 1.00 | Both expand wildcards and read the statements fine. |
| 4. Cross-statement reasoning | 1.00 | 1.00 | **The honest surprise.** Sonnet 4.6 already chains `PassRole`+`RunInstances` across statements *without* the skill. The fixture-02 lift (+1.67) therefore comes from criticality and no-false-positives, not from the combo being missed. On a weaker model item 4 would likely separate; on Sonnet the differentiator is discipline, not detection. |

The clean control (11) shows the largest single lift (+4.00). That is expected and is the point: a cold agent's instinct is to find something, and a correctly-scoped policy is the hardest thing for it to leave alone. The skill's value there is the discipline to report zero findings and spend the output on the boundary.

### Caveats on these specific numbers

- **N=3 per cell** is directional. A full run (`--trials 5`) would tighten the variance; several cells have a trial-to-trial std around 0.5–1.0, so individual fixtures can shift by ±0.5.
- **The one negative (05, −0.33)** is within that noise: control aced the NotAction fixture (7.00) and one treatment trial scored 6/7. It is not a methodology regression — both conditions handle `Allow`+`NotAction` well.
- **LLM-as-judge.** The judge is itself a model and can be wrong. Spot-check graded outputs (in `eval_results.json`) to calibrate trust.
- **Sonnet as agent.** A stronger agent (Opus) would likely raise control scores — especially on cross-statement reasoning, which Sonnet already passes — and shrink the absolute lift. The honest comparison is against the production model.

## What the eval does

For each fixture, the script runs N trials in two conditions:

- **Control**: the agent is given the raw IAM policy JSON (permissions policy, plus trust / boundary where present) and a generic "audit this policy for misconfigurations" prompt. It uses whatever it brings from training.
- **Treatment**: the agent is given the same JSON plus the full `SKILL.md` as the methodology to follow.

Each output is graded by an LLM judge against the 7-item rubric. The judge is given the deterministic reference audit (`_audit.py`, via `policies.py`) as ground truth, so grading is anchored to a known-good answer rather than the judge's own opinion.

## Files

| File | Purpose |
|---|---|
| `run_eval.py` | The runner. Calls the API in both conditions, calls the judge, aggregates. Resumable. Needs `ANTHROPIC_API_KEY`. |
| `run_until_pass.sh` | Drives `run_eval.py` fixture-by-fixture, retrying each until complete. Safe to interrupt. |
| `policies.py` | Per-fixture contexts and ground-truth findings (computed by importing `_audit.py`, so they never drift). Runs offline. |
| `rubric.md` | The 7-item rubric, one sentence per item. |
| `judge_prompt.md` | The judge prompt template, for swapping in a different judge. |

## When to re-run this

- After any non-trivial edit to `SKILL.md`. The prose is load-bearing; re-run with at least N=3 to catch regressions.
- After adding a worked example. If the lift on the new fixture is near zero, `SKILL.md` probably needs to cover that case.
- Before submitting the skill to a marketplace. A documented lift is a contributor-trust signal.

## What the eval does NOT measure

- **Narrative quality.** A correct finding stated tersely scores the same as one dressed up.
- **Speed / cost.** Token accounting is not part of the score (both conditions get the same budget; treatment loads the full SKILL.md and is expected to run longer).
- **Real-world generalization.** The eleven fixtures are constructed, not pulled from production. High lift here is a regression guard plus a credibility signal, not proof of operational value.

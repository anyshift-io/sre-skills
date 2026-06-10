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

Not yet scored. The harness is committed and reproducible; run `python tests/eval/run_eval.py --trials 5` (or `bash tests/eval/run_until_pass.sh 5`) to produce the numbers, then fill in the table below.

| Fixture | Control | Treatment |
|---|---:|---:|
| 02 PassRole + RunInstances (E1) | — | — |
| 04 UpdateFunctionCode (E3) | — | — |
| 09 Public trust policy (X1) | — | — |
| 11 Clean control | — | — |
| **Aggregate mean** | — | — |

### Where the lift is expected to come from

The per-item breakdown is the informative part. Based on the methodology's design and the sibling skills' measured runs, the lift should concentrate on:

| Rubric item | What a cold agent tends to do | What the skill should fix |
|---|---|---|
| 4. Cross-statement reasoning | Reads each statement, finds nothing individually damning on the PassRole-plus-RunInstances or two-attached-policies fixtures, and declares the policy fine. | Evaluates the union of statements and names the escalation combo. |
| 6. Boundary | Presents a single policy read as a complete access verdict; never mentions the permissions boundary, the other attached policies, or org SCPs. | Names the joins it cannot make. |
| 3. No false positives | On the clean control, invents a finding ("this looks broad"); on the public-trust fixture, may call a correctly-narrowed wildcard "public". | Returns zero findings on the control and respects the ExternalId/org narrowing. |
| 5. Criticality | Rates a broad read as critical, or an unscoped admin grant the same as a scoped one. | Headlines the escalation, downgrades the scoped PassRole, defers the read reach. |

Confirm or refute these once the eval is scored. If the lift on a fixture is near zero, `SKILL.md` probably needs to cover that case better; that signal is the whole point of committing the eval.

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

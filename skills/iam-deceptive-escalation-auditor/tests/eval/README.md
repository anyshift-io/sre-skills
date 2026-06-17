# Control-only screening eval

Is a dedicated `iam-deceptive-escalation-auditor` skill worth building? Only if a COLD agent (no skill, generic "review this policy for problems" prompt) already fails on this domain. This harness measures exactly that. There is **no SKILL.md and no treatment arm**: it runs the control condition only and reports whether the cold agent scores LOW.

The replay tests under `tests/replay_*.py` prove the reference engine produces the intended verdict on every fixture (six deceptive-clean, one buried-hard needle). This eval then runs a live agent against the same fixtures and scores it against a 7-item rubric ([`rubric.md`](./rubric.md)), anchored to that engine as ground truth.

**Screening rule:** build the skill only if the aggregate control mean is **< 4 / 7**. A high control score means the base model already handles deceptive IAM escalation and a skill adds little.

## Quickstart

```bash
# Install the only non-stdlib dependency
pip install anthropic

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Smoke test: 1 trial, 3 fixtures (two clean, one needle)
python tests/eval/run_eval.py --trials 1 --fixtures 02,05,08

# Full screen: 5 trials, all 7 fixtures (~70 LLM calls)
python tests/eval/run_eval.py --trials 5
```

The script writes raw per-trial results to `eval_results.json` and prints a per-fixture summary table with the aggregate control mean and a screening verdict. `python tests/eval/scenarios.py` prints the deterministic ground-truth findings for every fixture with **no API key required**.

## Resume / crash-safety

The eval is **resumable, and each trial is independent**. Every completed `(fixture, condition, trial)` cell is written to `eval_results.json` immediately via an atomic temp-file rename, and on startup the runner reloads what is already on disk and runs **only the missing cells**. So:

- An interrupt (`Ctrl-C`), a crash, or an API overload mid-run never throws away completed work.
- To finish a partial run, **re-run the exact same command** — it fills the gaps and stops.
- `run_eval.py` also wraps every API call in exponential backoff (`_with_retries`) over 429 / 5xx / "overloaded" errors.
- Pass `--fresh` to ignore an existing results file and start clean.

## The fixtures (why they are all in the cold agent's weak region)

Every fixture is engineered so a single-statement read gives the wrong answer. None is an obvious admin-star the base model trivially flags.

| Fixture | Engine verdict | The trap |
|---|---|---|
| 01 orphaned-passrole-deny | clean | PassRole + RunInstances both present, but an explicit `Deny` on `iam:PassRole` kills the combo. |
| 02 action-star-blanket-deny | clean | `Action '*'` pinned to one sandbox bucket (never Resource `*`), plus a `Deny` on every escalation service. |
| 03 assumerole-broken-trust | clean | `sts:AssumeRole` on an admin-sounding role whose trust does not point back; no `UpdateAssumeRolePolicy` to fix it. |
| 05 iam-mutation-boundary-capped | clean | A full mutation kit (PutRolePolicy/Attach/CreatePolicyVersion/UpdateAssumeRolePolicy/PassRole/CreateAccessKey) scoped to one break-glass ARN, fully capped by a permission-boundary-style `Deny` across Resource `*`. |
| 06 cross-account-assume-condition-gated | clean | A cross-account `sts:AssumeRole` that looks like a pivot but is sealed by an `aws:PrincipalOrgID` + `sts:ExternalId` Condition the principal cannot satisfy; the target trust's wildcard Principal is narrowed by the same condition (no X1). |
| 07 passrole-sandboxed-role-orphaned | clean | `iam:PassRole` + compute verbs (Start/Invoke) read like the launch combo, but the verbs bind no role and the one passable role is read-only: an orphaned escalation with no privilege gain. |
| 08 ml-platform-passrole-launch-needle | E1 (critical) | `iam:PassRole` (`*`) and `sagemaker:CreateTrainingJob` split four policies apart across six attached policies of benign ML-platform bait. |

The cold agent is expected to over-flag the six clean fixtures as critical privilege escalation (item 3), the proven capability gap, and to miss the one buried combo by reading each statement in isolation (item 4).

## What the eval does

For each fixture, the script runs N trials in the control condition: the agent is given the raw IAM policy JSON (permissions policy, plus trust where present) and a generic "audit this policy for misconfigurations" prompt. It uses whatever it brings from training. Each output is graded by an LLM judge against the 7-item rubric, anchored to the deterministic reference audit (`_audit.py`, via `scenarios.py`) as ground truth, so grading is against a known-good answer rather than the judge's own opinion.

## Files

| File | Purpose |
|---|---|
| `run_eval.py` | The control-only runner. Calls the API once per trial, calls the judge, aggregates. Resumable. Needs `ANTHROPIC_API_KEY`. |
| `scenarios.py` | Per-fixture contexts and ground-truth findings (computed by importing the copied `_audit.py`, so they never drift). Runs offline. |
| `rubric.md` | The 7-item rubric, one sentence per item. |
| `judge_prompt.md` | The judge prompt template, for swapping in a different judge. |

## What the eval does NOT measure

- **Lift.** There is no treatment arm; this screen measures only whether the cold baseline is weak enough to justify building the skill.
- **Narrative quality / speed / cost.** Not part of the score.
- **Real-world generalization.** The seven fixtures are constructed, not pulled from production. A low control score here is a *signal* that the domain is hard for a cold agent, not proof of operational value.

# Eval: s3-estate-calibration-auditor (control-vs-treatment lift)

Measures the lift the `s3-estate-calibration-auditor` `SKILL.md` gives over a cold agent on the
effective-exposure calibration across an S3 estate. Control is the cold agent on a generic
prompt; treatment prepends `SKILL.md` as the methodology. Both arms are graded against the same
deterministic engine ground truth, so the score delta is attributable to the skill.

## The experiment

The base model aces the obvious S3 needles (a loud public bucket, a clear cross-account grant:
~7.0). It is WEAK in a narrow region we located empirically: it **over-flags** BPA-neutralised /
scoped-clean estates (~2.67-3.67) and **misses** one subtly-buried public / cross-account needle
hidden among neutralised lookalikes (~3.67). This harness scopes every fixture to exactly that
region. In **control**, a cold agent gets the raw config for EVERY bucket in an 8-12 bucket
ESTATE and a GENERIC "review this for problems" prompt that does **not** name public exposure,
cross-account access, BPA neutralisation, or the buried needle. In **treatment**, the same
estate and ask are prefixed with `SKILL.md`. The question is the lift on getting the
effective-exposure CALIBRATION right -- not flagging the buckets that LOOK exposed but are
neutralised/scoped, and still catching the one quiet live needle.

Seven fixtures, all hard-region:

| Fixture | Verdict | What it tests |
|---|---|---|
| `01-media-platform-clean` | CLEAN (10 buckets) | ignored ACL + BPA-restricted policy + org/IP/AP-delegation scoping, no live |
| `02-data-lake-clean` | CLEAN (11) | neutralised policies + ignored ACL + org-path/external-id scoping |
| `03-saas-tenancy-clean` | CLEAN (9) | org/external-id scoped sharing + ignored ACL |
| `04-backup-estate-clean` | CLEAN (10) | BPA-neutralised policies + ignored ACL + SourceIp scoping |
| `05-logging-estate-needle` | NEEDLE: `XACCT-POLICY` | one cross-account policy (BPA-all-on bucket) buried among clean/neutralised |
| `06-analytics-estate-needle` | NEEDLE: `POLICY-PUBLIC` | one unconditional public policy hidden among conditional lookalikes |
| `07-partner-share-needle` | NEEDLE: `XACCT-ACL` | one cross-account canonical-user ACL among ignored public-ACL lookalikes |

4 deceptive-clean, 3 single-needle. No loud/obvious public bucket (the model already aces those).

## Run

```bash
export ANTHROPIC_API_KEY=...
pip install anthropic
python tests/eval/run_eval.py --trials 3                              # treatment arm (~42 LLM calls)
python tests/eval/run_eval.py --conditions control,treatment --trials 3   # both arms, full lift
python tests/eval/run_eval.py --conditions control --trials 1 --fixtures 01,06  # smoke test
python tests/eval/run_eval.py --trials 3 --fresh                      # ignore prior results
```

`--conditions` defaults to `treatment` (control cells from the original screening run are
reused from `eval_results.json`); pass `control,treatment` to run both arms in one pass.

Defaults: `--trials 3`, agent + judge `claude-sonnet-4-6`, results in `eval_results.json`.
Each trial is persisted atomically; re-run the same command to resume after an interrupt.

## Ground truth offline (no key)

```bash
python tests/eval/scenarios.py   # prints clean/needle verdict, live codes, needle bucket, baits
```

The judge is anchored to `scenarios.expected_estate()`, which runs the reused deterministic
engine (verbatim per-bucket `_resolve.py`, aggregated across the estate by `_estate.py`). The two
load-bearing rubric items are **item 2** (surfaces the buried live needle as a primary finding, on
the needle estates) and **item 3** (does not over-flag the neutralised / scoped baits, on the
deceptive-clean estates). See `rubric.md` and `judge_prompt.md`.

## Reading the result

The summary prints, per fixture, the control mean, the treatment mean, and the lift, plus the
two load-bearing item rates (item 2 surfaces the buried live needle, item 3 does not over-flag
the neutralised / scoped baits) for each arm. The skill is working when treatment lifts the
weak-region fixtures toward 6-7/7 and the item-2 / item-3 pass rates climb under treatment. The
weakest treatment fixture is the next one to close with a `SKILL.md` edit.

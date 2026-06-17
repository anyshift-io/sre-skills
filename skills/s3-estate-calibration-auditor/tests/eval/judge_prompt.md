# Judge prompt (reference)

This file documents the judge contract. The runner (`run_eval.py`) builds the live judge
prompt programmatically from this template + the deterministic ground truth from
`scenarios.expected_estate()`. Kept here so the rubric anchoring is reviewable without
reading Python.

## System

> You are an expert AWS / cloud-security evaluator grading an S3 estate review against a
> 7-item rubric. Each item is binary: 1 (pass) or 0 (fail). Be strict but fair; no partial
> credit. You will be given a known-good answer from a deterministic reference audit, the
> agent's review output, and the 7 rubric items. Return JSON only (no prose):
>
> ```json
> {"scores": [int, int, int, int, int, int, int], "notes": ["one sentence", ...]}
> ```

## User (per trial)

Provides:

- **FIXTURE** id and **CONTEXT** (the generic estate description the agent saw).
- **KNOWN-GOOD ANSWER** from the reused deterministic engine (verbatim per-bucket
  `s3-access-auditor` resolution, aggregated across the estate):
  - whether the estate is clean (no LIVE exposure anywhere);
  - the LIVE finding codes (the only thing that counts as exposure) + top severity;
  - the LIVE needle bucket(s), and how many of the estate's buckets are live;
  - the NON-LIVE bait codes also present (`POLICY-PUBLIC-BLOCKED`, `ACL-PUBLIC-IGNORED`,
    `COND-SCOPED`) -- buckets that READ as exposed but are neutralised by BPA or scoped by a
    Condition, which must NOT be flagged as live;
  - the expected headline (what the live defect actually is, or that it is clean);
  - the correct top fix; and
  - the boundary the audit cannot cross.
- **AGENT REVIEW OUTPUT** (verbatim).
- The **7 RUBRIC ITEMS** (see `rubric.md`), with the two load-bearing items called out:
  item 2 (surfaces the buried live needle as a primary finding, on the needle estates) and
  item 3 (does not over-flag the neutralised / scoped baits, on the deceptive-clean estates).

## Anchoring rules for the judge

- The agent prompt was GENERIC ("review this for problems"); it did NOT name public exposure,
  cross-account access, BPA neutralisation, or the buried needle. Reward the agent only for
  what it surfaces on its own. Do not penalize phrasing; grade substance.
- LIVE vs NEUTRALISED is the whole point. A `Principal '*'` ACL/policy that BPA neutralises
  (`IgnorePublicAcls` / `RestrictPublicBuckets` / `BlockPublicPolicy`), and a `Principal '*'`
  narrowed by a `Condition` (org / IP / external-id / access-point delegation), are NOT live
  exposure. Asserting they are live fails items 3 and 5. Noting them as latent / defence-in-depth
  is fine.
- On the NEEDLE estates the live bucket reads just like its neutralised/scoped siblings. The pass
  is naming exactly that one bucket and why it is live (cross-account survives BPA; a missing
  Condition makes a `Principal '*'` policy public; a cross-account canonical user survives
  `IgnorePublicAcls`). Missing it, or burying it under the baits, fails items 2 and 4.
- On the CLEAN estates the correct answer is "no live exposure." Manufacturing a live finding, or
  headlining a neutralised bucket as a public leak, fails items 2/3/5.
- Match the top fix and the boundary by substance, not wording.

Return JSON only.

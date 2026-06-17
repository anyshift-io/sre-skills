# Tests: s3-estate-calibration-auditor

Deterministic ground-truth + replay tests for the S3 estate-calibration fixtures. No API key,
no network, stdlib only. The replay tests pin the engine verdict on every fixture; the
control-vs-treatment lift eval under [`eval/`](./eval/) measures the `SKILL.md` against it.

## Engine (reused, not re-derived)

- `_resolve.py` — a **verbatim byte-for-byte copy** of the validated per-bucket engine from the
  sibling skill `s3-access-auditor/tests/_resolve.py`. The four-layer effective-access resolution
  (Block Public Access x bucket policy x bucket ACL x access points) is unchanged, so the ground
  truth here is provably the same computation.
- `_estate.py` — thin wrapper that re-exports the per-bucket engine and exposes
  `run_estate(fixture_dir) -> Estate`. It does NOT change engine logic. It runs the verbatim
  `run_resolve` on every bucket sub-directory of an estate, then aggregates: the `Estate` result
  exposes `.buckets` (per-bucket `Resolution`s) / `.live_buckets` / `.clean` / `.codes()` (LIVE
  codes only) / `.all_codes()` (live + baits) / `.top_severity` / `.needle_buckets` / `.boundary`.
  For this estate harness, the "aggregation across sub-items" is exactly this roll-up: the estate
  is clean iff NO bucket carries a live finding (`LIVE_CODES`), and the needle is whichever
  bucket(s) carry a live finding among the neutralised/scoped lookalikes.

`LIVE_CODES` = {`POLICY-PUBLIC`, `AP-PUBLIC`, `XACCT-POLICY`, `XACCT-ACL`, `ACL-PUBLIC`}. The
neutralised/scoped codes the engine also emits (`POLICY-PUBLIC-BLOCKED`, `ACL-PUBLIC-IGNORED`,
`COND-SCOPED`) read as exposed but are NOT live, and do not count toward the estate verdict.

## Replay tests

One per fixture; each asserts the ground-truth verdict (clean / which single needle):

```bash
for f in tests/replay_*.py; do python3 "$f"; done
```

| Fixture | Verdict | Live needle |
|---|---|---|
| `01-media-platform-clean` | CLEAN | none (all neutralised/scoped) |
| `02-data-lake-clean` | CLEAN | none |
| `03-saas-tenancy-clean` | CLEAN | none |
| `04-backup-estate-clean` | CLEAN | none |
| `05-logging-estate-needle` | `XACCT-POLICY` (high) | acme-log-shipping (cross-account, survives BPA-all-on) |
| `06-analytics-estate-needle` | `POLICY-PUBLIC` (critical) | acme-analytics-clickstream (no Condition, BPA not restricting) |
| `07-partner-share-needle` | `XACCT-ACL` (high) | acme-share-partner-drop (cross-account canonical user, survives IgnorePublicAcls) |

4 deceptive-clean, 3 single-needle. Each fixture is an estate of 8-12 buckets, all in the
hard-region distribution; every clean/needle estate is also seeded with neutralised/scoped baits
that the engine confirms are NOT live.

If a fixture and the engine disagree, **fix the fixture, never the engine** — the engine is the
validated oracle.

## Eval (lift)

`tests/eval/` holds the control-vs-treatment lift eval that measures the `SKILL.md`: control is
the cold agent on a generic prompt, treatment prepends `SKILL.md` as the methodology, both
graded against the same engine ground truth. See `tests/eval/README.md`.

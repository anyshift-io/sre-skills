# Rubric: s3-estate-calibration-auditor (control-only screening)

Seven binary items. Each is 1 (pass) or 0 (fail); no partial credit. The judge grades the
cold agent's audit of an S3 ESTATE (8-12 buckets) against the deterministic ground truth from
the reused per-bucket engine, aggregated across the estate (`_estate.py` -> verbatim
`_resolve.py`).

The agent was given a GENERIC prompt: the raw `public-access-block.json` / `bucket-policy.json`
/ `bucket-acl.json` / `access-points.json` for EVERY bucket in the estate, and "review this for
security/risk problems, rank by severity, give the top fix, and say what you cannot determine."
The prompt did NOT name public exposure, cross-account access, Block Public Access neutralisation,
the deceptive-clean baits, or the buried needle.

Every fixture is from the HARD region we located empirically. The cold agent aces obvious public
needles, so there are none here. Instead: 4 DECEPTIVE-CLEAN estates (several buckets LOOK exposed
but are genuinely neutralised by `IgnorePublicAcls` / `RestrictPublicBuckets` / a narrowing
`Condition`, so the engine reports NO live exposure) and 3 estates with exactly ONE quiet LIVE
needle buried among many neutralised lookalikes. The screening question is whether the cold agent
gets the effective-exposure CALIBRATION right: neither over-flagging the neutralised baits nor
missing the buried live needle.

1. **Parse.** Reads the four config layers per bucket (the BPA booleans in
   `public-access-block.json`, the Principal/Condition in `bucket-policy.json`, the Grantee in
   `bucket-acl.json`, `access-points.json`), and processes EVERY bucket in the estate, not just a
   couple. Recognises `IgnorePublicAcls` / `BlockPublicPolicy` / `RestrictPublicBuckets` as the BPA
   switches and a narrowing `Condition` (`aws:PrincipalOrgID`, `sts:ExternalId`, `aws:SourceIp`,
   `s3:DataAccessPoint*`) as scoping a `Principal '*'`.

2. **Surfaces the buried live needle (LOAD-BEARING).** On a NEEDLE estate, names the one genuinely
   live bucket (a cross-account policy, an unconditional public policy, or a cross-account
   canonical-user ACL) as A (the) PRIMARY finding, with the reason it is live, rather than burying
   it among the neutralised lookalikes or missing it. On a CLEAN estate, correctly reports NO live
   exposure. This is the item the cold agent most often misses on the needle estates: the live
   bucket reads just like its neutralised/scoped siblings.

3. **Does not over-flag the neutralised / scoped baits (LOAD-BEARING).** Does NOT report a bucket
   that is neutralised by BPA (`IgnorePublicAcls` / `RestrictPublicBuckets` / `BlockPublicPolicy`)
   or scoped by a narrowing `Condition` as a LIVE public/exposed bucket. A public-looking ACL with
   `IgnorePublicAcls` on, a `Principal '*'` policy with `RestrictPublicBuckets` on, and a
   `Principal '*'` narrowed by org / IP / external-id are NOT live exposure. Calling them live --
   or, on a clean estate, manufacturing any live finding -- fails this item. Noting them as latent
   / defence-in-depth is fine; asserting live public exposure is not. This is the item the cold
   agent most often fails on the deceptive-clean estates (the empirically-measured 2.67-3.67 region).

4. **Effective-access composition.** Resolves each bucket's EFFECTIVE verdict by combining BPA x
   policy x ACL x access points, not by reading one layer in isolation. Understands BPA neutralises
   PUBLIC grants but NOT cross-account grants (so BPA-all-on does not clear a cross-account
   policy/ACL), and that `IgnorePublicAcls` neutralises public GROUPS but not a cross-account
   canonical user. Does not clear a bucket on "BPA is all on" alone, nor condemn it on
   "`Principal '*'` is present" alone.

5. **Criticality.** Ranks the live needle as the headline (critical for a public policy, high for
   cross-account), and does NOT headline a neutralised/scoped bucket or (on a clean estate) invent a
   critical. Does not drown the real finding or the clean verdict in a wall of nitpicks about the
   correctly-neutralised buckets.

6. **Boundary.** Names at least one thing it cannot determine from the bucket configs alone,
   matching the ground-truth join: per-object ACLs, CloudFront/CDN fronting, the trusted account's
   identity policies, the account-level BPA dependency, or data sensitivity.

7. **Recommendation.** The top fix matches the ground truth in substance: fix / scope the one live
   bucket; or on a clean estate, no live fix beyond optional defence-in-depth and confirming the
   boundary. Does not prescribe ripping out the intentional scoped-sharing or the BPA-neutralised
   buckets as if they were live leaks.

## Verdict (computed from CONTROL means only)

- Aggregate control mean **< 4.0/7**, or a **majority** of fixtures below 4.0 -> **BUILD**
  (cold agent is weak here; the skill is worth writing).
- Aggregate **< 5.5/7** -> **MAYBE** (mixed; inspect per-fixture, especially items 2 and 3).
- Otherwise -> **SKIP** (cold agent already strong; the skill adds little).

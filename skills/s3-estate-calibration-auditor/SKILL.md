---
name: s3-estate-calibration-auditor
description: Audit an estate of AWS S3 buckets for the one bucket that is genuinely publicly or cross-account exposed, without over-flagging the many buckets that READ as exposed but are neutralised. Resolves each bucket's EFFECTIVE verdict by composing four layers (Block Public Access x bucket policy x bucket ACL x access points), never one layer alone, then rolls the per-bucket verdicts up into an estate verdict. Its discipline is symmetric: BPA (RestrictPublicBuckets / BlockPublicPolicy) neutralises a Principal '*' policy but NOT a cross-account grant; IgnorePublicAcls kills a public-group ACL grant but NOT a cross-account canonical-user grant; a narrowing Condition (org id, ExternalId, SourceIp, access-point delegation) scopes a Principal '*' so it is not public. On a needle estate it names the ONE live bucket as the primary finding; on a clean estate it reports NO live exposure and does not manufacture findings. Then it states what the bucket configs alone cannot answer (per-object ACLs, CloudFront/CDN fronting, the trusted principals' identity policies, account-level BPA dependency, data sensitivity). Use when asked to review an S3 bucket fleet for public exposure, cross-account access, or whether the estate is clean. Vendor-neutral; runs offline against describe-bucket / get-bucket-policy / get-bucket-acl / list-access-points JSON with no Anyshift account.
---

# s3-estate-calibration-auditor

Effective-exposure audit skill for an estate of AWS S3 buckets. Takes the config layers
for every bucket in the estate (`public-access-block.json`, `bucket-policy.json`,
`bucket-acl.json`, and `access-points.json` where present), resolves each bucket's
effective verdict by composing all four layers, then answers one question a per-layer
read cannot: across 8-12 buckets that mostly READ as exposed, which one is genuinely
live, and is the estate otherwise clean. It returns the live bucket as the headline,
ranked by severity, with a fix, then names exactly where the bucket configs stop being
able to answer the question.

Effective S3 exposure is a join across four layers that each get read wrong one at a
time. A public-looking bucket policy is inert under RestrictPublicBuckets; a cross-account
grant survives BPA-all-on; a public-group ACL is dead under IgnorePublicAcls but a
cross-account canonical user beside it is not; a clean bucket can still be public through
an access point. In an estate, the trap doubles: several buckets carry a Principal '*'
policy, an AllUsers ACL, or a wide-open look that is genuinely neutralised, and exactly
one bucket carries a real live grant that reads just like its neutralised siblings. This
skill composes the layers per bucket instead of clearing each layer in isolation, then
calibrates the estate: it does not over-flag the neutralised baits, and it does not miss
the buried needle.

## When to invoke

- An agent is asked to review an S3 bucket fleet for public exposure, cross-account
  access, or "is anything in this account public."
- An estate is being shipped or changed and the question is whether any bucket is
  effectively exposed, not just whether a Principal '*' or an AllUsers grant appears
  somewhere in the configs.
- An estate *looks* exposed (several Principal '*' policies, AllUsers ACLs) and the claim
  "but BPA is on / it is scoped" needs to be confirmed against the effective verdict
  rather than taken on trust.
- An estate *looks* locked down (BPA all on everywhere) and the claim "the account is
  closed" needs to be checked against the cross-account grants BPA does not touch.

## What this skill reads, and what it does not

It reads the static configuration of an **estate of buckets**: per bucket, any subset of
the Block Public Access booleans, the bucket policy, the bucket ACL, and the access
points. Those are S3 control-plane reads (`get-public-access-block`, `get-bucket-policy`,
`get-bucket-acl`, `list-access-points` + `get-access-point-policy`). That is the entire
input. The audit is correct and complete *for what the bucket configs can tell you*, and
it is explicit about the rest. Reachability-on-paper is not exposure-in-fact, and every
audit ends by naming the joins it cannot make:

- It does **not** see **per-object ACLs**. An individual object can carry its own
  public-read grant even when the bucket is private. Join: bucket config to its per-object
  ACLs.
- It does **not** see **CloudFront / CDN fronting**. A bucket can be private while its data
  is served publicly through a CloudFront distribution with Origin Access Control. Join:
  bucket to its CDN distribution.
- It does **not** contain the **privileges of a trusted principal**. A cross-account or
  conditional grant only matters in proportion to what the trusted account/role can do and
  whether it re-shares onward, which lives in *that* account. Join: this bucket to the
  identity policies of the principals it trusts.
- It does **not** see **VPC-endpoint policies or org SCPs**, which can further restrict
  access this config Allows. Join: bucket to its VPC-endpoint policies and the org SCPs.
- A flagged grant's **exploitability** depends on the **data sensitivity** of the objects,
  which is not in the config.

A clean (deceptive-clean) estate still gets a boundary section, because a BPA-neutralised
estate is not a proven-safe system: turning BPA off would expose the latent statements.

## The model

For **every bucket** in the estate, build the **effective verdict** by composing four
layers. Never read one layer alone. A finding is LIVE only when a real public or
cross-account grant survives the layer that would neutralise it:

1. **Block Public Access (BPA)** -- four booleans that *neutralise* otherwise-public
   policy and ACL grants, but do NOT touch cross-account grants.
2. **The bucket policy** -- a resource policy whose Principal can be public ('*'), a named
   other account, or '*' narrowed by a Condition.
3. **The bucket ACL** -- legacy grants to canonical users, or to the AllUsers /
   AuthenticatedUsers public groups.
4. **Access points** -- each with its OWN BPA and policy, able to expose data
   independent of (but not exceeding) the bucket.

The estate is **clean iff no bucket is live**. The needle is whichever bucket carries a
live finding among many neutralised/scoped lookalikes.

## The methodology, in order

### 1. Parse all four layers for every bucket

Before any judgment, read each layer for each bucket. Process EVERY bucket in the estate,
not the first couple:

- **BPA**: read the four booleans from `public-access-block.json`. An absent file means
  all four are False (no BPA). The two that *neutralise existing grants* are
  `RestrictPublicBuckets` / `BlockPublicPolicy` (for a public policy) and
  `IgnorePublicAcls` (for a public-group ACL). `BlockPublicAcls` only blocks *new* public
  ACLs and does not disable an existing one.
- **Policy**: read each `Statement` in `bucket-policy.json`. A `Deny` grants nothing and
  cannot make a bucket public; classify only the `Allow` statements. For each Allow, read
  the `Principal` (public '*', a named AWS account, or '*' with a Condition) and the
  `Condition`.
- **ACL**: read each grant in `bucket-acl.json`. A Grantee that is the AllUsers or
  AuthenticatedUsers `Group` URI is a public-group grant; a `CanonicalUser` that is not the
  bucket owner is a cross-account grant; an owner-only ACL produces nothing.
- **Access points**: read each entry in `access-points.json`. Each AP has its OWN
  `PublicAccessBlock` and `Policy`; resolve the AP policy exactly like a bucket policy,
  against the AP's own BPA.

Recognise the BPA switches by name, and recognise a narrowing Condition: `aws:PrincipalOrgID`,
`aws:PrincipalOrgPaths`, `aws:PrincipalAccount`, `aws:PrincipalArn`, `aws:SourceArn`,
`aws:SourceAccount`, `aws:SourceVpc`, `aws:SourceVpce`, `aws:SourceIp`, `aws:VpcSourceIp`,
`sts:ExternalId`, and the access-point delegation keys `s3:DataAccessPointAccount` /
`s3:DataAccessPointArn` / `s3:AccessPointNetworkOrigin`. Any of these on a Principal '*'
scopes it to a bounded caller set.

**Read each bucket's BPA booleans verbatim — do not let a bucket's name or its grants tell
you what they are.** Each boolean being `true` is the **safe** direction: `IgnorePublicAcls:
true` means an existing public ACL is ignored (dead); `RestrictPublicBuckets: true` means a
public policy is denied. Do not invert it. The dominant miscalibration is asserting a boolean
value to fit an expectation: a bucket named `exports`, `public`, `share`, `partner`, or `cdn`,
or any bucket carrying an `AllUsers` / `AuthenticatedUsers` grant, invites the assumption that
it *must* be the exposed one — and that assumption makes you misread its `IgnorePublicAcls` as
`false`. In these estates the **common** case is the opposite: a shareable-sounding bucket with
an `AllUsers` grant and `IgnorePublicAcls: true`, which is **neutralised**, not live. The
presence of a grant is not evidence about the boolean. To keep the transcription faithful: for
any bucket carrying an `AllUsers` / `AuthenticatedUsers` ACL grant or a `Principal '*'` policy,
**paste that bucket's entire `public-access-block.json` as a verbatim JSON block** before you
classify it, and read the four booleans out of the pasted block. Pasting the raw object is
harder to get wrong than filling a value in from memory, which is where the misread creeps in.

### 2. Resolve each bucket's effective verdict (the composition)

Compose the layers; do not condemn a bucket on "Principal '*' is present" alone, and do not
clear it on "BPA is on" alone. The codes:

- **POLICY-PUBLIC (critical, LIVE)** -- the bucket policy allows Principal '*' with NO
  narrowing Condition, and BPA is NOT restricting (RestrictPublicBuckets and
  BlockPublicPolicy both off). Live public exposure: anyone on the internet can perform the
  granted actions.
- **AP-PUBLIC (critical, LIVE)** -- an access point's own policy allows Principal '*' with
  no Condition and the AP's own BPA is not restricting. Data is reachable publicly through
  the access point even when the bucket policy and bucket BPA are clean. Auditing only the
  bucket misses this.
- **XACCT-POLICY (high, LIVE)** -- the bucket policy grants a named other account. This is
  NOT public, so BPA does not govern it: a cross-account grant stays fully live even with
  all four BPA switches on. The classic misread is seeing BPA-all-on and calling the bucket
  locked down.
- **XACCT-ACL (high, LIVE)** -- the bucket ACL grants a canonical user that is not the
  bucket owner. IgnorePublicAcls neutralises the public GROUPS, not a named canonical user,
  so this grant survives BPA-all-on. A TLS-only Deny in the policy does not address it.
- **ACL-PUBLIC (high, LIVE)** -- the bucket ACL grants the AllUsers / AuthenticatedUsers
  group and IgnorePublicAcls is OFF. Live public via ACL, independent of the bucket policy.

These five are the only codes that count as live exposure. The next three READ as exposed
but are NOT live, and must never be reported as a live public/exposed bucket:

- **POLICY-PUBLIC-BLOCKED (info, neutralised)** -- a Principal '*' policy that
  RestrictPublicBuckets / BlockPublicPolicy renders inert. Effective verdict: NOT public.
  Note it as latent risk (turning BPA off would expose it), not as live exposure.
- **ACL-PUBLIC-IGNORED (info, neutralised)** -- a public-group ACL grant that
  IgnorePublicAcls makes ineffective. Effective verdict: NOT public via this ACL.
- **COND-SCOPED (low, scoped)** -- a Principal '*' narrowed by a Condition (org / IP /
  source account or VPC / ExternalId / access-point delegation). This is conditional or
  org-scoped sharing, NOT public: a caller outside the condition is denied. Reading
  Principal '*' and stopping there is the misread this guards against.

### 3. Surface the buried live needle (LOAD-BEARING)

On a NEEDLE estate, name the ONE genuinely live bucket as A (the) PRIMARY finding, with the
reason it is live, instead of burying it among the neutralised lookalikes or missing it. The
live bucket reads just like its neutralised/scoped siblings; the pass is naming exactly that
one and why:

- A **cross-account** policy or ACL survives BPA-all-on (XACCT-POLICY / XACCT-ACL): BPA only
  neutralises public grants.
- A **missing Condition** makes a Principal '*' policy public (POLICY-PUBLIC) when its
  scoped-looking siblings carry an org id / ExternalId / SourceIp.
- A **named canonical user** survives IgnorePublicAcls (XACCT-ACL) when the AllUsers grants
  beside it are correctly ignored.

State the live bucket by name, the code, and the layer it is grounded in.

### 4. Stay quiet on the deceptive-clean estate (LOAD-BEARING)

This is the half the naive read gets wrong in the other direction. An estate where every
bucket is neutralised or scoped is **CLEAN**, and the audit must say so instead of
manufacturing a finding. The composition in step 2 is what proves it. Specifically:

- A **public-looking ACL with IgnorePublicAcls on** is not live. Do not report it as a
  public bucket.
- A **Principal '*' policy with RestrictPublicBuckets / BlockPublicPolicy on** is not live.
  Do not report it as a public bucket.
- A **Principal '*' narrowed by org / IP / external-id / access-point delegation** is scoped
  sharing, not public. Do not read Principal '*' and call it public.
- Do not drown the clean verdict, or the one real finding, in a wall of nitpicks about the
  correctly-neutralised buckets.

On a clean estate the audit reports: NO live exposure anywhere, *why* the exposed-looking
buckets are neutralised or scoped (the BPA switch or the Condition), and the boundary. It
does **not** invent a critical. Noting the neutralised statements as latent / defence-in-depth
is fine; asserting live public exposure is not.

### 5. Rank and report, then name the boundary

Order findings by severity (critical for a public policy or public access point, high for a
cross-account or public-group grant). Rank the live needle as the headline; do NOT headline a
neutralised/scoped bucket, and on a clean estate do not invent a critical. For each finding:
the bucket and layer it is grounded in, what the exposure is, and the fix. Then list the
boundary from "What this skill reads." A clean estate still gets a boundary section.

## Recommendations

Fix the live bucket; do not rip out intentional scoped sharing or the BPA-neutralised
buckets as if they were live leaks:

- **POLICY-PUBLIC / AP-PUBLIC**: remove the public statement, or replace Principal '*' with
  the specific accounts/roles that need access. If public read is genuinely intended (a
  static site), front it with CloudFront + Origin Access Control instead of a public bucket
  or access point, and turn RestrictPublicBuckets on.
- **XACCT-POLICY / XACCT-ACL**: confirm the other account is a deliberate, current trust and
  the actions are minimal; scope to specific prefixes and prefer an `aws:PrincipalOrgID` /
  `sts:ExternalId` condition over a bare account root. For an ACL grant, express the sharing
  as a scoped bucket policy and disable ACLs with Bucket Owner Enforced. BPA-all-on does not
  make a cross-account bucket safe.
- **ACL-PUBLIC**: remove the public ACL grant and set IgnorePublicAcls + BlockPublicAcls;
  prefer bucket policies over ACLs.
- **Neutralised / scoped buckets (POLICY-PUBLIC-BLOCKED, ACL-PUBLIC-IGNORED, COND-SCOPED)**:
  no live fix. As defence in depth, optionally remove the latent public statement or ignored
  ACL so the bucket does not depend on BPA staying on as its only guardrail; for a scoped
  bucket, confirm the condition value (the org id, the ExternalId, the SourceIp CIDRs) is the
  intended one and leave the grant in place if the scope is correct.

## Severity model

| Severity | Meaning |
|---|---|
| **critical** | Live public exposure: a Principal '*' bucket policy with BPA not restricting (POLICY-PUBLIC), or a public access-point policy (AP-PUBLIC). |
| **high** | Live cross-account or public-group exposure that BPA does not close: cross-account policy (XACCT-POLICY), cross-account canonical-user ACL (XACCT-ACL), public-group ACL with IgnorePublicAcls off (ACL-PUBLIC). |
| **low** | A Principal '*' scoped by a Condition (COND-SCOPED): conditional sharing to verify, not public exposure. |
| **info** | A neutralised grant present but inert (POLICY-PUBLIC-BLOCKED, ACL-PUBLIC-IGNORED): latent risk if BPA is turned off, not live exposure. |

Only the critical and high bands are LIVE exposure and count toward the estate verdict. The
low and info bands are exposed-looking-but-not-live; they are notes, never the headline.

## Rule reference

| Code | Rule | Severity | Live | Grounded in |
|---|---|---|---|---|
| POLICY-PUBLIC | Bucket policy Principal '*', no Condition, BPA not restricting | critical | yes | bucket policy x BPA |
| AP-PUBLIC | Access-point policy Principal '*', AP BPA not restricting | critical | yes | access-point policy x AP BPA |
| XACCT-POLICY | Bucket policy grants a named other account | high | yes | bucket policy (BPA does not touch it) |
| XACCT-ACL | Bucket ACL grants a non-owner canonical user | high | yes | bucket ACL (IgnorePublicAcls does not touch it) |
| ACL-PUBLIC | Bucket ACL grants AllUsers / AuthenticatedUsers, IgnorePublicAcls off | high | yes | bucket ACL x BPA |
| COND-SCOPED | Principal '*' narrowed by a Condition | low | no | bucket policy Condition |
| POLICY-PUBLIC-BLOCKED | Principal '*' policy neutralised by RestrictPublicBuckets / BlockPublicPolicy | info | no | bucket policy x BPA |
| ACL-PUBLIC-IGNORED | Public-group ACL neutralised by IgnorePublicAcls | info | no | bucket ACL x BPA |

The matching half of every live rule is the clean verdict: POLICY-PUBLIC neutralised to
POLICY-PUBLIC-BLOCKED, ACL-PUBLIC neutralised to ACL-PUBLIC-IGNORED, a Principal '*' scoped to
COND-SCOPED, on an estate of these is the correct, complete output, not a failure to find
something. Reporting a neutralised bucket as a live leak is the dominant failure mode this
skill prevents.

## Output format

The agent's final message in any invocation must include:

1. **Estate**: bucket count, the entry question (public exposure across the estate).
2. **Findings**: ranked by severity, each with the code, the bucket and layer it is grounded
   in, what the exposure is, and the fix. The live needle named explicitly as the headline.
   Or "no live exposure" for a deceptive-clean estate, stating *why* the exposed-looking
   buckets are neutralised or scoped.
3. **Boundary**: the joins this audit could not make (per-object ACLs, CloudFront/CDN
   fronting, the trusted principals' identity policies, the account-level BPA dependency, VPC
   endpoint policies / org SCPs, data sensitivity), stated explicitly so the gap is visible
   instead of silent.

## Worked examples

Seven end-to-end fixtures are committed under `fixtures/`, each an estate of 8-12 buckets
with a runnable replay test. The set is deliberately weighted toward deceptive-clean, because
over-flagging a neutralised estate is the cold agent's dominant failure here. No loud, obvious
public bucket appears: the base model already aces those.

- [`05-logging-estate-needle`](./fixtures/05-logging-estate-needle/): the needle. acme-log-shipping
  has all four BPA switches on (reads as locked down) but its policy grants a named other
  account read/list. A cross-account grant survives BPA: XACCT-POLICY (high), live.
- [`06-analytics-estate-needle`](./fixtures/06-analytics-estate-needle/): acme-analytics-clickstream
  grants Principal '*' GetObject with NO Condition and BPA not restricting, sitting next to
  siblings that carry an org id / ExternalId or have RestrictPublicBuckets on: POLICY-PUBLIC
  (critical), live.
- [`07-partner-share-needle`](./fixtures/07-partner-share-needle/): acme-share-partner-drop
  grants READ to another account's canonical user via its ACL; IgnorePublicAcls (on for this
  estate) only ignores the AllUsers lookalikes beside it: XACCT-ACL (high), live.
- [`01-media-platform-clean`](./fixtures/01-media-platform-clean/): an AllUsers ACL, a Principal
  '*' policy, org/IP-scoped policies, and an access-point delegation, all neutralised or scoped.
  Clean.
- [`02-data-lake-clean`](./fixtures/02-data-lake-clean/): public-looking policies and a public
  ACL, all neutralised by BPA or scoped by org-path / external-id. Clean.
- [`03-saas-tenancy-clean`](./fixtures/03-saas-tenancy-clean/): tenant-shared buckets scoped by
  org id / ExternalId, plus one ignored AllUsers ACL. Clean.
- [`04-backup-estate-clean`](./fixtures/04-backup-estate-clean/): BPA-neutralised policies, an
  ignored public ACL, and a SourceIp office allowlist. Clean.

## Replay tests

Every fixture has a replay test in `tests/` that runs the methodology (via the deterministic
reference engine `tests/_resolve.py`, aggregated across the estate by `tests/_estate.py`)
against the committed JSON, with no external credentials. Run from the skill directory:

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

The seven tests cover the three needle estates (the one live code fires, on the named bucket)
and the four deceptive-clean estates (no live finding fabricated). Tests exit non-zero if the
audit names the wrong bucket or invents one on a clean estate. See
[`tests/README.md`](./tests/README.md) for the fixture schema.

## Failure modes

This skill is wrong in predictable ways. Read [`FAILURE_MODES.md`](./FAILURE_MODES.md) before
relying on it. Highlights:

- It audits effective access *on paper*, not exploitability. A live grant can reach a tier
  with no sensitive objects, or one fronted by a CDN, or one whose trusted account does
  nothing with it. Exposure-on-paper is a hypothesis to confirm, not a breach.
- A clean verdict depends on BPA staying on. The neutralised buckets are one BPA toggle away
  from live; "clean" means clean today, not proven-safe.
- It reasons over the four bucket-config layers only. A public object ACL, a CloudFront
  distribution, a per-object grant, or an account-level BPA the per-bucket config does not
  carry is outside the graph this skill builds.

## Anyshift integration (opt-in)

The audit above runs end-to-end against the bucket-config JSON the user already has. No
Anyshift dependency.

Every boundary note in this skill is a join: bucket to its per-object ACLs, bucket to its
CloudFront distribution, bucket to the identity policies of the principals it trusts, bucket
to its VPC-endpoint policies and org SCPs, estate to the account-level BPA the neutralisation
depends on. The Anyshift MCP can act as a context primer by resolving those joins from a
versioned resource graph, so an XACCT-POLICY finding ("cross-account, real only if the trusted
account is privileged or re-shares") can be closed instead of deferred at the boundary. A
measured "with vs without" delta will be published here once the integration has been
exercised against the replay fixtures.

# Failure modes: s3-estate-calibration-auditor

This skill composes the effective public/cross-account verdict across each bucket's four
config layers and rolls them up into an estate verdict. It is correct for what those configs
express and wrong in the predictable ways below. Read this before acting on a finding.

## 1. Effective exposure is not exploitability

A LIVE finding means a real public or cross-account grant survives the layer that would
neutralise it. It does **not** mean data is actually exposed or that the grant is reachable.
Each of these breaks an exposure-on-paper without changing a single bucket-config line:

- **No CDN context.** A bucket can be private while its objects are served publicly through a
  CloudFront distribution with Origin Access Control, and a flagged public bucket may sit
  behind a CDN that adds its own controls. The skill does not read the distribution.
- **The trusted principal does nothing.** A cross-account grant only matters in proportion to
  what the trusted account/role can do with it and whether it re-shares onward, neither of
  which is in this bucket config.
- **Data sensitivity.** A public or cross-account read on a bucket of public marketing assets
  is not the same finding as one on a bucket of PII; the config cannot tell you which.

The boundary section of every audit names these. A LIVE finding is a hypothesis to confirm
against the live estate, not a proven breach.

## 2. "Clean" means neutralised today, not safe

A clean verdict (no LIVE bucket) means every exposed-looking bucket is neutralised by BPA
(`IgnorePublicAcls` / `RestrictPublicBuckets` / `BlockPublicPolicy`) or scoped by a Condition.
It does **not** prove the estate is safe:

- The neutralisation depends on **account-level and bucket-level BPA staying on**. Turning a
  BPA switch off re-arms every POLICY-PUBLIC-BLOCKED and ACL-PUBLIC-IGNORED bucket into a live
  public bucket. Clean is one toggle away from exposed.
- A **per-object public ACL** (section 4) can make an object public even when the bucket is
  clean.
- A scoped grant's safety rests on the **condition value** being the intended one; a stale
  `aws:SourceIp` CIDR or a wrong org id is still scoped, just to the wrong scope.

The clean verdict always ships with the boundary, for exactly this reason. Do not read "clean"
as "audited and proven private."

## 3. BPA neutralisation is asymmetric, and it is easy to over-apply

BPA neutralises **public** grants and **only** public grants. The two mistakes:

- **Clearing on BPA-all-on alone.** Seeing all four BPA switches on and concluding the bucket
  is locked down is wrong: a cross-account bucket policy (XACCT-POLICY) and a cross-account
  canonical-user ACL (XACCT-ACL) are fully live with BPA all on. This is exactly how the
  needle hides on the logging and partner-share estates.
- **Condemning on Principal '*' alone.** Seeing a Principal '*' and calling the bucket public
  is wrong when `RestrictPublicBuckets` / `BlockPublicPolicy` is on (POLICY-PUBLIC-BLOCKED) or
  when a narrowing Condition scopes it (COND-SCOPED). `IgnorePublicAcls` kills the AllUsers
  group but not a named canonical user; `BlockPublicAcls` blocks only *new* public ACLs, not
  the existing grant. Reading the wrong BPA switch as the neutraliser produces the wrong
  verdict.

## 4. Only the four bucket-config layers are in scope

The verdict is composed from exactly four inputs per bucket: `public-access-block.json`,
`bucket-policy.json`, `bucket-acl.json`, `access-points.json`. Outside that set:

- **Per-object ACLs** are not the bucket config. An object can be public-read while the bucket
  is private; this skill cannot see it.
- **CloudFront / CDN fronting, VPC-endpoint policies, and org SCPs** can add or remove access
  this config does not show. A bucket that looks private to this skill may be served publicly
  by a CDN; one that looks open may be capped by an SCP.
- **Account-level BPA** (as opposed to the per-bucket BPA in the fixture) can neutralise a
  grant the bucket config alone reports as live. If only the bucket-level config is supplied,
  the verdict is for that config.

## 5. The needle is one bucket; do not stop at the first one

On a needle estate exactly one bucket is live among many neutralised/scoped lookalikes. Two
symmetric mistakes:

- **Missing it** by reading each bucket's most prominent layer in isolation (the cross-account
  needle hides behind BPA-all-on; the public needle hides among conditional siblings; the
  cross-account ACL hides among ignored AllUsers grants).
- **Over-flagging the siblings** by calling the neutralised/scoped lookalikes live, which
  buries the real finding in noise. The estate verdict is "clean iff no bucket is live" and
  "the needle is the one live bucket"; both halves are load-bearing.

Process every bucket; do not generalise from the first two or three.

## 6. The estate config is what was supplied, not the whole account

The estate verdict is over the buckets and layers handed to the audit. If a bucket was omitted,
or a layer (its policy, its ACL, its access points) was not supplied, a real live grant or a
neutralising BPA setting may be missing, and the verdict is incomplete. A clean estate means
"clean across the configs supplied," not "this account has no public bucket." Escalate to a
human when the estate inventory is uncertain, when a flagged cross-account or public grant
needs a business-intent decision (is the trust deliberate, is the public read intended), or
when closing a boundary join (per-object ACLs, the CDN, the trusted account's privileges)
requires reads this skill does not perform.

## 7. Residual over-flag variance on neutralised buckets (measured)

This is a measured reliability limit of the agent applying the skill, not a gap in the
methodology, and it does not fully close with prompting or a deterministic decode. On a minority
of runs the agent reports a **neutralised** bucket as live — typically by asserting
`IgnorePublicAcls: false` (and thus an `ACL-PUBLIC` finding) when the actual config says
`true`. The misread happens *inside* the step-1 mitigations (read the boolean verbatim, paste
the raw `public-access-block.json` block) and persists at temperature 0: the value is
hallucinated within the pasted block.

What measurably triggers it: a bucket that carries an `AllUsers` / `AuthenticatedUsers` ACL
grant, especially with a name that suggests exposure (`exports`, `public`, `share`, `partner`,
`cdn`). The name plus the grant primes "this is the exposed one," and the boolean is then read
to fit that expectation.

Scale, from the control/treatment eval (temperature 0, 3 trials/fixture): the skill lifts the
"does not over-flag the neutralised baits" item from a control pass rate of **0.00** to **0.76**
— a large, real improvement, but not 1.0. Six of seven estates land at or near a clean 7/7;
the over-flag surfaces intermittently across the deceptive-clean estates and most frequently on
`03-saas-tenancy` (the `acme-tenant-exports` bucket), which oscillates between 7/7 and a
false-positive ~3/7. The deterministic reference engine is always correct; the variance is in
the model's transcription of the boolean.

Operational guidance: when this skill reports a bucket as live `ACL-PUBLIC` or `POLICY-PUBLIC`,
**re-read that bucket's `public-access-block.json` directly** before acting — confirm the
quoted `IgnorePublicAcls` / `RestrictPublicBuckets` value against the source. A single live
finding on a shareable-sounding bucket with an `AllUsers` grant is the case most worth
double-checking, precisely because it is the case the model is most likely to get wrong.

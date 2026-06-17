"""
Per-fixture estate contexts and expected answers for the s3-estate-calibration-auditor
screening eval.

The "expected_*" fields are the deterministic answers from the reused engine (_estate.py,
which delegates to the validated per-bucket _resolve.py) run against each estate fixture.
They are the source of truth the LLM judge compares the agent's output against, so the
findings are computed here by importing the engine rather than hand-copied (which would drift).

load_fixture_text renders the FULL volume the agent sees: EVERY bucket in the estate and
EVERY config layer it has (public-access-block.json / bucket-policy.json / bucket-acl.json /
access-points.json) -- an 8-12 bucket haystack per fixture, no pre-filtering. The control
prompt (in run_eval.py) is deliberately GENERIC and does NOT name public exposure,
cross-account access, BPA neutralisation, or the calibration vector; these expected fields
exist only for the judge, never for the agent.

Stdlib only. No external dependencies. `python scenarios.py` prints ground truth, no key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = TESTS_DIR.parent / "fixtures"

sys.path.insert(0, str(TESTS_DIR))
from _estate import run_estate  # noqa: E402

# Each entry pairs an estate fixture with the GENERIC context the eval feeds the agent
# (an estate description, no vector hint), plus the headline / fix / boundary the
# deterministic engine grounds (the judge's anchor only). Keep aligned with replay_*.py.
SCENARIOS = [
    {
        "id": "01-media-platform-clean",
        "estate": "media-platform",
        "context": "A 10-bucket media platform estate (origin, thumbnails, uploads, transcode temp, CDN logs, office exports, an access-point-fronted delivery bucket, archive, staging, shared config). Asked to review the estate's public-exposure posture.",
        "expected_headline": "NO live exposure anywhere in the estate. Several buckets READ as exposed -- an AllUsers READ ACL, a Principal '*' GetObject policy, Principal '*' narrowed by org id / SourceIp, an access-point delegation -- but every one is neutralised by Block Public Access (IgnorePublicAcls / RestrictPublicBuckets) or scoped by a Condition. The correct verdict is clean. Do NOT report any of these neutralised/scoped buckets as a live public bucket.",
        "expected_top_fix": "None for live exposure. Optionally, as defence in depth, remove the latent public ACL grant and the public-looking policy statements so the estate does not depend on BPA staying on as its only guardrail, but nothing is live today.",
        "expected_boundary_join": "per-object ACLs (an object can be public even when the bucket is private), whether a CloudFront distribution serves any bucket publicly, the account-level BPA settings (turning BPA off would expose the latent statements), and data sensitivity; the bucket configs alone cannot complete the effective-exposure join.",
    },
    {
        "id": "02-data-lake-clean",
        "estate": "data-lake",
        "context": "An 11-bucket data lake estate (raw, curated, glue scripts, athena results, EMR logs, an export bucket, quarantine, checkpoints, models, feature store, temp). Asked to review the estate's public-exposure posture.",
        "expected_headline": "NO live exposure anywhere. Multiple buckets carry public-looking policies and a public ACL grant, but all are neutralised by BPA (RestrictPublicBuckets / IgnorePublicAcls) or scoped by a Condition (aws:PrincipalOrgPaths, sts:ExternalId). The correct verdict is clean. Do NOT over-flag the neutralised lake buckets as live.",
        "expected_top_fix": "None for live exposure. Defence-in-depth: drop the latent public statements and the ignored public ACL so the lake is not one BPA toggle away from exposure, but nothing is live today.",
        "expected_boundary_join": "per-object ACLs, CloudFront/CDN fronting, the account-level BPA settings the bucket policies depend on, and the identity policies of any org/external-id principals the scoped grants trust; not derivable from the bucket configs alone.",
    },
    {
        "id": "03-saas-tenancy-clean",
        "estate": "saas-tenancy",
        "context": "A 9-bucket multi-tenant SaaS estate (tenant assets, uploads, billing, a partner feed, exports, config, backups, logs, search index). Asked to review the estate's public-exposure posture.",
        "expected_headline": "NO live exposure anywhere. Several tenant-shared buckets use Principal '*' narrowed by aws:PrincipalOrgID or sts:ExternalId (scoped sharing, not public), and one AllUsers ACL grant is rendered inert by IgnorePublicAcls. The correct verdict is clean. Do NOT read Principal '*' and call these buckets public.",
        "expected_top_fix": "None for live exposure. Confirm the org id and external id on the scoped buckets are the intended values; defence-in-depth, remove the ignored public ACL. Nothing is live today.",
        "expected_boundary_join": "the identity policies of the org accounts / external-id partner that the scoped grants trust (org membership scopes WHO, not WHAT they can do), per-object ACLs, and the account BPA settings; not in the bucket configs.",
    },
    {
        "id": "04-backup-estate-clean",
        "estate": "backup-estate",
        "context": "A 10-bucket backup/DR estate (daily, weekly, snapshots, db dumps, a restore staging bucket, an office share, config, vault, glacier archive, test restore). Asked to review the estate's public-exposure posture.",
        "expected_headline": "NO live exposure anywhere. A few buckets carry public-looking policies and a public ACL grant, all neutralised by BPA (RestrictPublicBuckets / IgnorePublicAcls); one Principal '*' is narrowed by an aws:SourceIp office allowlist (IP-scoped, not public). The correct verdict is clean. Do NOT over-flag the neutralised backup buckets.",
        "expected_top_fix": "None for live exposure. Defence-in-depth: remove the latent public statements and the ignored public ACL; confirm the SourceIp CIDRs are current office ranges. Nothing is live today.",
        "expected_boundary_join": "per-object ACLs, the account BPA settings the neutralisation depends on, whether the SourceIp ranges are still the intended office network, and data sensitivity; not in the bucket configs alone.",
    },
    {
        "id": "05-logging-estate-needle",
        "estate": "logging-estate",
        "context": "An 11-bucket logging estate (app, access, cloudtrail, vpc flow, elb, a log-shipping bucket, waf, cloudfront, archive, metrics, audit). Asked to review the estate's public-exposure posture.",
        "expected_headline": "Exactly one LIVE finding, buried among clean and neutralised buckets: acme-log-shipping has all four Block Public Access switches on (which reads as locked down) but its bucket policy grants a named other account (905638217741) read/list. A cross-account grant is NOT public, so BPA does not block it: it is fully live. The other buckets (a BPA-neutralised public policy, an ignored public ACL, an org-scoped policy) are NOT live and must not be flagged.",
        "expected_top_fix": "On acme-log-shipping, confirm account 905638217741 is a deliberate, current trust and the actions are minimal; scope to specific prefixes and prefer an aws:PrincipalOrgID / sts:ExternalId condition over a bare account root. BPA-all-on does not make this bucket safe.",
        "expected_boundary_join": "the identity policies of the trusted account 905638217741 (what it can actually do with the grant and whether it re-shares onward), which live in that account; plus per-object ACLs. Not in this bucket config.",
    },
    {
        "id": "06-analytics-estate-needle",
        "estate": "analytics-estate",
        "context": "A 10-bucket analytics estate (an org-shared events bucket, dashboards, a partner extract, reports, clickstream, ML features, staging, warehouse, ingest, temp). Asked to review the estate's public-exposure posture.",
        "expected_headline": "Exactly one LIVE finding, hidden among conditional lookalikes: acme-analytics-clickstream grants Principal '*' s3:GetObject with NO Condition and BPA is not restricting (RestrictPublicBuckets and BlockPublicPolicy both off), so it is live public. It sits next to sibling buckets that look identical but carry an aws:PrincipalOrgID or sts:ExternalId condition (scoped, fine) or have RestrictPublicBuckets on (neutralised, fine). The needle is the one missing its Condition block; the scoped/neutralised siblings must not be flagged.",
        "expected_top_fix": "On acme-analytics-clickstream, remove the public statement or scope the Principal to named accounts; if public read is genuinely intended, front it with CloudFront + Origin Access Control and turn RestrictPublicBuckets on. The conditional sibling buckets are intentional scoped sharing and should be left alone.",
        "expected_boundary_join": "per-object ACLs and the data sensitivity of the clickstream objects (the config cannot tell you what is exposed), and the account BPA setting the verdict depends on; not in the bucket config.",
    },
    {
        "id": "07-partner-share-needle",
        "estate": "partner-share",
        "context": "A 9-bucket partner-sharing estate (a public mirror, a press kit, a partner drop, downloads, uploads, config, an org feed, archive, staging). Asked to review the estate's public-exposure posture.",
        "expected_headline": "Exactly one LIVE finding, disguised as a routine ACL: acme-share-partner-drop grants READ to a different account's CANONICAL USER via its bucket ACL. IgnorePublicAcls (on for this estate) only neutralises the public GROUPS (AllUsers / AuthenticatedUsers); a cross-account canonical-user grant is untouched and stays live even with BPA tightened, and the bucket's TLS-only Deny does not address it. The lookalike buckets carry AllUsers public ACL grants that ARE ignored by IgnorePublicAcls (not live) -- the needle reads like them but is a named other identity, not a public group.",
        "expected_top_fix": "On acme-share-partner-drop, remove the cross-account ACL grant unless it is a deliberate, current sharing relationship; express any intended sharing as a scoped bucket policy with a named principal and disable ACLs with Bucket Owner Enforced. The TLS Deny does not cover the partner's read access.",
        "expected_boundary_join": "the identity policies of the trusted account behind the canonical user (what it can do, whether it re-shares), and the per-object ACLs; the cross-account ACL grant's blast radius is not in this bucket config.",
    },
]


def fixture_dir(scenario: dict) -> Path:
    return FIXTURES_DIR / scenario["id"]


def load_fixture_text(scenario: dict) -> str:
    """The raw config JSON the agent is given for this estate.

    Renders the FULL volume: EVERY bucket sub-directory in the estate and EVERY config
    layer it has (BPA, policy, ACL, access points), so the agent genuinely sees the
    8-12 bucket haystack, not a pre-filtered slice. NOTE: the agent prompt itself
    (run_eval.py) is generic and does not name public exposure / cross-account / BPA.
    """
    d = fixture_dir(scenario)
    layers = [
        ("public-access-block.json", "BLOCK PUBLIC ACCESS (public-access-block.json)"),
        ("bucket-policy.json", "BUCKET POLICY (bucket-policy.json)"),
        ("bucket-acl.json", "BUCKET ACL (bucket-acl.json)"),
        ("access-points.json", "ACCESS POINTS (access-points.json)"),
    ]
    bucket_dirs = sorted(
        child for child in d.iterdir()
        if child.is_dir() and any((child / f).exists() for f, _ in layers)
    )
    parts: list[str] = [f"S3 estate '{scenario['estate']}' -- {len(bucket_dirs)} buckets, "
                        "raw config exactly as returned by the S3 API:"]
    for bd in bucket_dirs:
        meta_path = bd / "meta.json"
        bucket_name = bd.name
        if meta_path.exists():
            bucket_name = json.loads(meta_path.read_text()).get("bucket", bd.name)
        parts.append("\n" + "=" * 78)
        parts.append(f"BUCKET: {bucket_name}")
        parts.append("=" * 78)
        for filename, label in layers:
            path = bd / filename
            if path.exists():
                parts.append(f"{label}:\n" + json.dumps(json.loads(path.read_text()), indent=2))
    return "\n".join(parts)


def expected_estate(scenario: dict) -> dict:
    """Run the reused deterministic engine to get the ground-truth verdict for the judge.

    The engine runs the verbatim per-bucket resolution on every bucket in the estate, then
    aggregates: the estate is clean iff no bucket carries a live finding, and the needle is
    whichever bucket(s) carry a live finding among the neutralised/scoped lookalikes.
    """
    e = run_estate(fixture_dir(scenario))
    return {
        "codes": sorted(e.codes()),                 # LIVE codes only
        "all_codes": sorted(e.all_codes()),         # live + neutralised/scoped baits
        "top_severity": e.top_severity,
        "clean": e.clean,
        "needle_buckets": e.needle_buckets,
        "bucket_count": e.bucket_count,
        "live_bucket_count": len(e.live_buckets),
        "boundary_count": len(e.boundary),
    }


# Alias kept for parity with the sibling harnesses' naming.
expected_resolution = expected_estate


if __name__ == "__main__":
    # `python tests/eval/scenarios.py` prints the ground-truth answers, no API key needed.
    for s in SCENARIOS:
        exp = expected_estate(s)
        needle = ", ".join(exp["needle_buckets"]) if exp["needle_buckets"] else "(none -- clean)"
        print(f"{s['id']:<30} clean={exp['clean']!s:<5} top={str(exp['top_severity']):<9} "
              f"live={str(exp['codes']):<20} buckets={exp['bucket_count']}")
        print(f"{'':<30} live_needle={needle}")
        print(f"{'':<30} baits(non-live)={sorted(set(exp['all_codes']) - set(exp['codes']))}")

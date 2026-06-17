"""
Reference implementation of the s3-access-auditor methodology.

This module is a deterministic stand-in for what an AI agent does when it
follows SKILL.md. It exists so replay tests can assert that the methodology,
applied to a known S3 bucket configuration, resolves the *effective* public and
cross-account access correctly, and names the boundary (what a bucket config
alone cannot answer).

The reason this skill exists is that effective S3 exposure is a join across four
layers that each get read wrong one at a time:

  1. Block Public Access (BPA) -- four booleans that *neutralise* otherwise-public
     policy and ACL grants, but do NOT touch cross-account grants.
  2. The bucket policy -- a resource policy whose Principal can be public ('*'),
     a named other account, or '*' narrowed by a Condition (org / IP / ExternalId).
  3. The bucket ACL -- legacy grants to canonical users or to the AllUsers /
     AuthenticatedUsers public groups.
  4. Access points -- each with its OWN BPA and policy, able to expose data
     independent of (but not exceeding) the bucket.

A reviewer who reads any single layer in isolation gets the wrong verdict: a
public-looking policy is inert under RestrictPublicBuckets (fixture 02); a
cross-account grant survives BPA-all-on (fixture 05); a clean bucket can still be
public through an access point (fixture 08). The methodology resolves the EFFECTIVE
verdict by combining all four, then names the joins it still cannot make.

Stdlib only. No external dependencies. No credentials. Runs anywhere Python 3.10+ runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# The two ACL groups that mean "the public internet". A grant to either is a
# public ACL grant; any other Grantee (a CanonicalUser, an AWS account) is not.
_PUBLIC_ACL_GROUPS = (
    "http://acs.amazonaws.com/groups/global/AllUsers",
    "http://acs.amazonaws.com/groups/global/AuthenticatedUsers",
)

# Condition keys that narrow an otherwise-public Principal '*' down to a bounded
# set of callers. A Principal '*' carrying one of these is conditional/scoped
# access, NOT unconditionally public.
_NARROWING_CONDITION_KEYS = (
    "aws:PrincipalOrgID",
    "aws:PrincipalOrgPaths",
    "aws:PrincipalAccount",
    "aws:PrincipalArn",
    "aws:SourceArn",
    "aws:SourceAccount",
    "aws:SourceVpc",
    "aws:SourceVpce",
    "aws:SourceIp",
    "aws:VpcSourceIp",
    "sts:ExternalId",
    # S3 access-point delegation: a bucket policy may delegate to access points in a
    # named account. This scopes the grant to AP requests from that account, not the
    # public, so a Principal '*' carrying it is delegation, not public exposure.
    "s3:DataAccessPointAccount",
    "s3:DataAccessPointArn",
    "s3:AccessPointNetworkOrigin",
)


@dataclass
class Finding:
    """One effective-access conclusion, derived from the bucket config layers."""

    code: str          # PUB-POLICY, PUB-ACL, XACCT-POLICY, XACCT-ACL, AP-PUBLIC, COND-SCOPED
    severity: str      # critical | high | medium | low | info
    attribute: str     # the layer / grant the finding is grounded in
    title: str
    detail: str
    recommendation: str


@dataclass
class Resolution:
    """Structured output of the methodology, one per bucket."""

    bucket: str
    findings: list[Finding] = field(default_factory=list)
    # The wall: questions the bucket config alone cannot answer. Each names a join
    # (to object ACLs, to the trusted principals' identity policies, to the CDN /
    # VPC / SCP layer) the resolution cannot make.
    boundary: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return len(self.findings) == 0

    @property
    def top_severity(self) -> str | None:
        if not self.findings:
            return None
        return min(self.findings, key=lambda f: _SEVERITY_RANK[f.severity]).severity

    def codes(self) -> set[str]:
        return {f.code for f in self.findings}


# --- Loading and normalisation -------------------------------------------------------


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def _statements(policy: dict | None) -> list[dict]:
    if not isinstance(policy, dict):
        return []
    return [s for s in _as_list(policy.get("Statement")) if isinstance(s, dict)]


# --- BPA model -----------------------------------------------------------------------


@dataclass
class Bpa:
    """The four Block Public Access booleans. Absent file => all four False (no BPA)."""

    block_public_acls: bool = False
    ignore_public_acls: bool = False
    block_public_policy: bool = False
    restrict_public_buckets: bool = False

    @classmethod
    def from_json(cls, doc: dict | None) -> "Bpa":
        d = doc or {}
        return cls(
            block_public_acls=bool(d.get("BlockPublicAcls", False)),
            ignore_public_acls=bool(d.get("IgnorePublicAcls", False)),
            block_public_policy=bool(d.get("BlockPublicPolicy", False)),
            restrict_public_buckets=bool(d.get("RestrictPublicBuckets", False)),
        )

    @property
    def neutralises_public_policy(self) -> bool:
        """RestrictPublicBuckets or BlockPublicPolicy makes a public BUCKET POLICY inert.

        RestrictPublicBuckets denies the public principal at evaluation time;
        BlockPublicPolicy refuses to evaluate/add a public policy. Either one means
        a Principal '*' policy grants nothing to the public. Neither touches
        cross-account grants.
        """
        return self.restrict_public_buckets or self.block_public_policy

    @property
    def neutralises_public_acls(self) -> bool:
        """IgnorePublicAcls makes existing public-GROUP ACL grants ineffective.

        BlockPublicAcls only blocks *new* public ACLs; IgnorePublicAcls is the one
        that disables the grants already present. Neither touches a cross-account
        canonical-user ACL grant.
        """
        return self.ignore_public_acls


# --- Principal / condition classification --------------------------------------------


def _statement_is_narrowed(stmt: dict) -> bool:
    """True if a Condition block scopes the statement to a bounded caller set."""
    condition = stmt.get("Condition")
    if not isinstance(condition, dict):
        return False
    for operator_block in condition.values():
        if isinstance(operator_block, dict) and any(k in _NARROWING_CONDITION_KEYS for k in operator_block):
            return True
    return False


def _principal_is_public(principal: Any) -> bool:
    """True if the Principal is the public wildcard '*' (string or {"AWS": "*"})."""
    if principal == "*":
        return True
    if isinstance(principal, dict):
        for value in principal.values():
            if value == "*" or (isinstance(value, list) and "*" in value):
                return True
    return False


def _cross_account_principals(principal: Any) -> list[str]:
    """The named AWS principals (account roots / ARNs) in a Principal block.

    These are NOT public: a specific other account. Returns the concrete values so
    the finding can name who is trusted. A '*' is handled by _principal_is_public.
    """
    out: list[str] = []
    if isinstance(principal, dict):
        for key, value in principal.items():
            if key != "AWS":
                continue
            for v in _as_list(value):
                if isinstance(v, str) and v != "*":
                    out.append(v)
    return out


def _condition_summary(stmt: dict) -> str:
    """A short human description of the narrowing condition keys present."""
    condition = stmt.get("Condition")
    keys: list[str] = []
    if isinstance(condition, dict):
        for operator_block in condition.values():
            if isinstance(operator_block, dict):
                keys.extend(k for k in operator_block if k in _NARROWING_CONDITION_KEYS)
    return ", ".join(dict.fromkeys(keys)) or "a Condition"


# --- Bucket-policy resolution --------------------------------------------------------


def _resolve_bucket_policy(policy: dict | None, bpa: Bpa, source: str = "bucket policy") -> list[Finding]:
    """Resolve the effective verdict of one resource policy (bucket or access-point).

    Walks each Allow statement and classifies its Principal:
      - public '*' with no narrowing condition  -> PUBLIC, unless BPA neutralises it
      - public '*' WITH a narrowing condition    -> conditional/scoped (not public)
      - a named other account                    -> cross-account (BPA does not block)
    """
    findings: list[Finding] = []
    for stmt in _statements(policy):
        if stmt.get("Effect") != "Allow":
            continue  # a Deny does not grant access; it cannot make a bucket public
        principal = stmt.get("Principal")
        actions = ", ".join(_as_list(stmt.get("Action"))) or "(unspecified actions)"

        if _principal_is_public(principal):
            if _statement_is_narrowed(stmt):
                cond = _condition_summary(stmt)
                findings.append(Finding(
                    code="COND-SCOPED", severity="low",
                    attribute=f"{source}: Principal '*' narrowed by {cond}",
                    title=f"Conditional access ({cond}), not unconditionally public",
                    detail=(
                        f"The {source} grants Principal '*' ({actions}) but a Condition on "
                        f"{cond} scopes it to a bounded set of callers (an organization, an IP "
                        "range, a source account/VPC, or an ExternalId). This is conditional or "
                        "org-scoped access, NOT public: a caller outside the condition is denied. "
                        "Reading Principal '*' and stopping there is the misread this flags against."
                    ),
                    recommendation=(
                        "Treat as intentional scoped sharing. Confirm the condition value is the "
                        "intended org / IP / account, and that the allowed actions match the "
                        "sharing intent. Do not 'fix' it by removing the grant if the scope is correct."
                    ),
                ))
            elif bpa.neutralises_public_policy:
                # The trap fixture: a public-looking policy that BPA renders inert.
                findings.append(Finding(
                    code="POLICY-PUBLIC-BLOCKED", severity="info",
                    attribute=f"{source}: Principal '*' present but neutralised by BPA",
                    title="Public policy statement present but neutralised by Block Public Access",
                    detail=(
                        f"The {source} contains a Principal '*' Allow ({actions}) that READS as "
                        "public, but BlockPublicPolicy / RestrictPublicBuckets is on, so the public "
                        "principal is denied at evaluation time and gets nothing. Effective verdict: "
                        "NOT public. The trap is reading the policy alone and calling the bucket "
                        "public; the BPA layer overrides it. Note it as latent risk (turning BPA off "
                        "would expose it), not as live exposure."
                    ),
                    recommendation=(
                        "Effective access is not public today. Remove the public statement anyway so "
                        "the bucket does not depend on BPA staying on as its only guardrail (defence in depth)."
                    ),
                ))
            else:
                findings.append(Finding(
                    code="POLICY-PUBLIC", severity="critical",
                    attribute=f"{source}: Principal '*' Allow ({actions})",
                    title="Bucket policy grants public access (Principal '*', no condition, BPA not restricting)",
                    detail=(
                        f"The {source} allows Principal '*' to {actions} with no narrowing Condition, "
                        "and Block Public Access does not restrict it (RestrictPublicBuckets and "
                        "BlockPublicPolicy are both off). Anyone on the internet can perform these "
                        "actions. This is live public exposure, not a latent risk."
                    ),
                    recommendation=(
                        "Remove the public statement, or replace Principal '*' with the specific "
                        "accounts/roles that need access. If public read is genuinely intended (a "
                        "static site), front it with CloudFront + Origin Access Control instead of a "
                        "public bucket, and turn RestrictPublicBuckets on."
                    ),
                ))
            continue

        cross = _cross_account_principals(principal)
        if cross:
            findings.append(Finding(
                code="XACCT-POLICY", severity="high",
                attribute=f"{source}: cross-account Principal {', '.join(cross)}",
                title="Bucket policy grants cross-account access (not blocked by Block Public Access)",
                detail=(
                    f"The {source} grants {', '.join(cross)} ({actions}). This is NOT public, so it is "
                    "not what Block Public Access governs: BPA only neutralises *public* grants. A "
                    "cross-account grant to a specific account ARN remains fully live even with all "
                    "four BPA switches on. The common misread is seeing BPA-all-on and concluding the "
                    "bucket is locked down; it is open to the trusted account."
                ),
                recommendation=(
                    "Confirm the other account is a deliberate, current trust relationship and that "
                    "the granted actions are minimal. Scope to specific prefixes/objects, and prefer "
                    "an aws:PrincipalOrgID or sts:ExternalId condition over a bare account root."
                ),
            ))
    return findings


# --- ACL resolution ------------------------------------------------------------------


def _resolve_acl(acl: dict | None, bpa: Bpa) -> list[Finding]:
    """Resolve effective ACL grants: public-group grants vs cross-account canonical users.

    Owner-only ACLs produce nothing. A public-group grant is neutralised by
    IgnorePublicAcls; a cross-account canonical-user grant is NOT (BPA never touches it).
    """
    findings: list[Finding] = []
    if not isinstance(acl, dict):
        return findings
    owner_id = (acl.get("Owner") or {}).get("ID")
    for grant in _as_list(acl.get("Grants")):
        if not isinstance(grant, dict):
            continue
        grantee = grant.get("Grantee") or {}
        permission = grant.get("Permission", "(unknown)")
        gtype = grantee.get("Type")
        uri = grantee.get("URI")
        gid = grantee.get("ID")

        if gtype == "Group" and uri in _PUBLIC_ACL_GROUPS:
            group = uri.rsplit("/", 1)[-1]
            if bpa.neutralises_public_acls:
                findings.append(Finding(
                    code="ACL-PUBLIC-IGNORED", severity="info",
                    attribute=f"ACL: {group} {permission} (ignored)",
                    title="Public ACL grant present but ignored by IgnorePublicAcls",
                    detail=(
                        f"The bucket ACL grants the {group} group {permission}, which reads as public, "
                        "but IgnorePublicAcls is on, so the grant is ineffective: it sits in the ACL and "
                        "grants nothing. Effective verdict: NOT public via this ACL. The trap is flagging "
                        "the grant as live without checking IgnorePublicAcls."
                    ),
                    recommendation=(
                        "Effective access is not public today. Remove the public ACL grant anyway so the "
                        "bucket does not depend on IgnorePublicAcls as its only guardrail."
                    ),
                ))
            else:
                findings.append(Finding(
                    code="ACL-PUBLIC", severity="high",
                    attribute=f"ACL: {group} {permission}",
                    title="Bucket ACL grants public access (IgnorePublicAcls is off)",
                    detail=(
                        f"The bucket ACL grants the {group} group {permission}, and IgnorePublicAcls is "
                        "off, so the grant is live: anyone on the internet has this permission. Public via "
                        "ACL, independent of the bucket policy (which may be empty)."
                    ),
                    recommendation=(
                        "Remove the public ACL grant and set IgnorePublicAcls + BlockPublicAcls. Prefer "
                        "bucket policies over ACLs for any sharing; disable ACLs entirely with Bucket "
                        "Owner Enforced if no legacy consumer needs them."
                    ),
                ))
            continue

        # A canonical-user grant to someone other than the bucket owner is a cross-account
        # (or cross-identity) ACL grant. BPA's IgnorePublicAcls does NOT touch it.
        if gtype == "CanonicalUser" and gid and gid != owner_id:
            name = grantee.get("DisplayName") or gid[:16]
            findings.append(Finding(
                code="XACCT-ACL", severity="high",
                attribute=f"ACL: canonical user {name} {permission}",
                title="Bucket ACL grants cross-account access (not blocked by Block Public Access)",
                detail=(
                    f"The bucket ACL grants {permission} to a canonical user ({name}) that is not the "
                    "bucket owner. This is a cross-account/cross-identity grant, not a public-group grant, "
                    "so IgnorePublicAcls does NOT neutralise it: it stays live even with BPA all-on. The "
                    "misread is assuming BPA-all-on closes every ACL grant; it only closes the public groups."
                ),
                recommendation=(
                    "Remove the cross-account ACL grant unless it is a deliberate, current sharing "
                    "relationship; express any intended sharing as a scoped bucket policy with a named "
                    "principal, not an ACL. Disable ACLs with Bucket Owner Enforced where possible."
                ),
            ))
    return findings


# --- Access-point resolution ---------------------------------------------------------


def _resolve_access_points(access_points: list | None) -> list[Finding]:
    """Each access point has its OWN BPA + policy and can expose data via the AP ARN.

    An AP cannot exceed the bucket's grants, but a public AP policy (not restricted by the
    AP's own BPA) is public-via-AP even when the bucket policy is clean.
    """
    findings: list[Finding] = []
    for ap in _as_list(access_points):
        if not isinstance(ap, dict):
            continue
        name = ap.get("Name", "(unnamed access point)")
        ap_bpa = Bpa.from_json(ap.get("PublicAccessBlock"))
        ap_findings = _resolve_bucket_policy(ap.get("Policy"), ap_bpa, source=f"access point '{name}'")
        for f in ap_findings:
            # Re-key public AP exposure to its own code so the AP layer is unmistakable.
            if f.code == "POLICY-PUBLIC":
                findings.append(Finding(
                    code="AP-PUBLIC", severity="critical",
                    attribute=f.attribute,
                    title=f"Access point '{name}' is public (its policy grants Principal '*', AP BPA not restricting)",
                    detail=(
                        f"Access point '{name}' has its own Public Access Block (with "
                        "BlockPublicPolicy/RestrictPublicBuckets off) and a policy granting Principal "
                        "'*'. Data in the bucket is reachable publicly THROUGH this access point even "
                        "if the bucket policy and bucket BPA are clean. Access points carry independent "
                        "BPA and policy; auditing only the bucket misses this entirely."
                    ),
                    recommendation=(
                        "Remove the public statement from the access-point policy, or turn on the access "
                        "point's RestrictPublicBuckets. If public delivery is intended, front it with "
                        "CloudFront + OAC rather than a public access point."
                    ),
                ))
            else:
                findings.append(f)
    return findings


# --- Boundary -------------------------------------------------------------------------


def _boundary_notes(has_cross_account: bool, has_access_points: bool) -> list[str]:
    notes = [
        "Object-level ACLs are not in the bucket config. An individual object can carry its own "
        "public-read grant even when the bucket is private. Join: bucket config to per-object ACLs.",
        "Effective data exposure depends on what the trusted principals can actually DO. A "
        "cross-account or conditional grant only matters in proportion to the identity policies of "
        "the accounts/roles it trusts, which live in those accounts. Join: this bucket to the IAM "
        "identity policies of the principals it trusts.",
        "Whether the bucket is fronted by CloudFront with Origin Access Control (so the bucket is "
        "private but the data is served publicly through the CDN) is not visible from the bucket "
        "config. Join: bucket to its CloudFront / CDN distribution.",
        "VPC-endpoint policies and Organization SCPs can further restrict access this config Allows, "
        "and are invisible from the bucket alone. Join: bucket to its VPC-endpoint policies and org SCPs.",
    ]
    if has_cross_account:
        notes.append(
            "A cross-account grant's blast radius is what the trusted account does with it (and whether "
            "it re-shares onward); neither is in this bucket config. Join: the trusted account to its own use."
        )
    if has_access_points:
        notes.append(
            "Each access point can have a VPC-only NetworkOrigin or further conditions that change who "
            "can reach it; confirm the AP's NetworkOrigin and any policy conditions. Join: access point "
            "to its network origin and consumers."
        )
    return notes


# --- Orchestration --------------------------------------------------------------------


def run_resolve(fixture_dir: Path) -> Resolution:
    """End-to-end: load the four config layers for one bucket and resolve effective access.

    Loads (any subset of): `public-access-block.json`, `bucket-policy.json`,
    `bucket-acl.json`, `access-points.json`. A `meta.json` may carry the bucket name.
    Resolves the EFFECTIVE verdict across BPA + policy + ACL + access points, then names
    the boundary (the joins a bucket config alone cannot make).
    """
    fixture_dir = Path(fixture_dir)

    bpa = Bpa.from_json(_load_json(fixture_dir / "public-access-block.json"))
    bucket_policy = _load_json(fixture_dir / "bucket-policy.json")
    bucket_acl = _load_json(fixture_dir / "bucket-acl.json")
    access_points = _load_json(fixture_dir / "access-points.json")

    meta = _load_json(fixture_dir / "meta.json") or {}
    bucket = meta.get("bucket", fixture_dir.name)

    findings: list[Finding] = []
    findings += _resolve_bucket_policy(bucket_policy, bpa, source="bucket policy")
    findings += _resolve_acl(bucket_acl, bpa)
    findings += _resolve_access_points(access_points)

    findings.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.code))

    has_cross_account = any(f.code in ("XACCT-POLICY", "XACCT-ACL") for f in findings)
    has_access_points = bool(_as_list(access_points))

    return Resolution(
        bucket=bucket,
        findings=findings,
        boundary=_boundary_notes(has_cross_account, has_access_points),
    )

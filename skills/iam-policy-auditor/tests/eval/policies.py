"""
Per-fixture principal contexts and expected answers, used by run_eval.py.

The "expected_*" fields are the deterministic answers from _audit.py run against
each fixture (see tests/replay_*.py). They are the source of truth the judge model
compares the agent's output against, so the findings are computed here by importing
the reference implementation rather than hand-copied (which would drift).

Stdlib only. No external dependencies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = TESTS_DIR.parent / "fixtures"

sys.path.insert(0, str(TESTS_DIR))
from _audit import run_audit  # noqa: E402

# Each entry pairs a fixture with the human-readable context the eval feeds the agent,
# plus the headline / fix / boundary the deterministic audit grounds (the judge's anchor).
# Keep this list aligned with the replay_*.py files under tests/.
POLICIES = [
    {
        "id": "01-admin-star",
        "principal": "role/ci-deployer",
        "role": "A CI deployment role with an inline policy left wide during bootstrap.",
        "expected_headline": "Action '*' on Resource '*' is full administrator; every escalation path is a subset of this one grant.",
        "expected_top_fix": "Replace the wildcard with the specific actions and ARNs needed, or attach AdministratorAccess explicitly behind a permissions boundary if admin is truly intended.",
        "expected_boundary_join": "principal to its permissions boundary (a boundary could cap even this), and to the org SCPs.",
    },
    {
        "id": "02-passrole-runinstances",
        "principal": "role/build-fleet-manager",
        "role": "Manages an EC2 build fleet; also granted iam:PassRole in a separate statement.",
        "expected_headline": "iam:PassRole (on Resource '*') plus ec2:RunInstances is a privilege escalation: launch an instance with any role attached, then use its credentials. Neither statement is alarming alone.",
        "expected_top_fix": "Scope iam:PassRole to the exact role ARNs the workload must pass (never '*'), with an iam:PassedToService condition.",
        "expected_boundary_join": "iam:PassRole to the privileges of the roles it can pass (which are not in this policy).",
    },
    {
        "id": "03-create-policy-version",
        "principal": "role/pipeline-policy-manager",
        "role": "Manages a family of pipeline policies; also allowed to read a deploy-config bucket.",
        "expected_headline": "iam:CreatePolicyVersion / SetDefaultPolicyVersion lets the principal rewrite a managed policy in place to grant admin, with no second action and no change to the policy's ARN.",
        "expected_top_fix": "Remove the policy-versioning actions unless this is a policy-administration role, and scope Resource to the specific policy ARNs.",
        "expected_boundary_join": "the policy ARNs it can version, and what attaching those policies could grant.",
    },
    {
        "id": "04-update-function-code",
        "principal": "role/lambda-deployer",
        "role": "Allowed to push code to any function in the account; PassRole scoped to the lambda-exec role path.",
        "expected_headline": "lambda:UpdateFunctionCode hijacks the execution role of any function the principal can target: overwrite its code, run as its role. No PassRole needed; one is present anyway.",
        "expected_top_fix": "Scope lambda:UpdateFunctionCode to the specific function ARNs deployed, and ensure those functions' execution roles are no more privileged than the principal.",
        "expected_boundary_join": "the execution roles of the targetable functions (whether any outranks this principal).",
    },
    {
        "id": "05-not-action-allow",
        "principal": "role/data-platform-operator",
        "role": "Intended as 'everything except the dangerous services', written with Allow + NotAction.",
        "expected_headline": "Effect Allow with NotAction grants every action in AWS except the few listed, including every future action and service. The shape reads narrow and is one of the broadest possible.",
        "expected_top_fix": "Invert to Effect Allow with an explicit Action allow-list; use NotAction only with Effect Deny.",
        "expected_boundary_join": "the permissions boundary and org SCPs that may (or may not) cap this near-total grant.",
    },
    {
        "id": "06-attach-policy-self",
        "principal": "role/service-onboarding",
        "role": "Provisions service roles; iam:AttachRolePolicy scoped to the service-role path.",
        "expected_headline": "iam:AttachRolePolicy lets the principal attach AdministratorAccess to a role it provisions (and can assume). Resource-scoping to a role path does not prevent the self-grant.",
        "expected_top_fix": "Remove policy-attachment unless this is an identity-administration role; if kept, cap it with a permissions boundary and scope to specific principals.",
        "expected_boundary_join": "the principals it can attach to, and whether it can assume any of them.",
    },
    {
        "id": "07-update-assume-role",
        "principal": "role/access-administrator",
        "role": "Manages who can assume which role; allowed iam:UpdateAssumeRolePolicy and a broad sts:AssumeRole.",
        "expected_headline": "iam:UpdateAssumeRolePolicy plus sts:AssumeRole is the full escalation: rewrite a privileged role's trust to trust this principal, then assume it.",
        "expected_top_fix": "Remove iam:UpdateAssumeRolePolicy unless this is a role-administration identity, and scope its Resource to the roles it legitimately manages.",
        "expected_boundary_join": "the privileges of the roles whose trust it can rewrite.",
    },
    {
        "id": "08-service-wildcard-exfil",
        "principal": "role/reporting-exporter",
        "role": "A reporting job that needs a couple of secrets and a few buckets, granted with secretsmanager:* and a broad s3 read.",
        "expected_headline": "secretsmanager:* hands over every secret in the account (high); s3:GetObject/ListBucket on Resource '*' is a broad read reach (low, depends on data classification). Two wildcards, two severities.",
        "expected_top_fix": "Scope both to the specific secrets and buckets the job needs; the s3 reach is a flag to verify against data classification, not a confirmed leak.",
        "expected_boundary_join": "what data the in-range buckets/secrets hold (a classification question the policy cannot answer).",
    },
    {
        "id": "09-public-trust-policy",
        "principal": "role/partner-data-reader",
        "role": "Permissions policy scoped to one bucket; trust policy left open to any principal for a partner integration.",
        "expected_headline": "The permissions policy is clean. The trust policy allows Principal '*' to assume the role with no ExternalId / org condition: any principal in any account can assume it.",
        "expected_top_fix": "Pin the trust to specific principal ARNs, or add an aws:PrincipalOrgID / sts:ExternalId condition.",
        "expected_boundary_join": "the account's IAM identity policies (the effective access of whoever assumes the role).",
    },
    {
        "id": "10-scoped-passrole-boundary",
        "principal": "role/batch-submitter",
        "role": "Runs batch jobs; iam:PassRole scoped to one role with a PassedToService condition, and a permissions boundary is attached.",
        "expected_headline": "The same PassRole + RunInstances combo as fixture 02, but PassRole is scoped to one role ARN: high, not critical. The escalation is real only if role/batch-worker outranks this principal, which is behind the boundary.",
        "expected_top_fix": "Confirm role/batch-worker is no more privileged than this principal; the scoping and PassedToService condition are already the right shape.",
        "expected_boundary_join": "the privileges of role/batch-worker (the one role it can pass).",
    },
    {
        "id": "11-clean-least-privilege",
        "principal": "role/orders-processor",
        "role": "A least-privilege worker: read one table, write one bucket prefix, decrypt with one key via one service.",
        "expected_headline": "No findings. Every grant is scoped to a specific ARN, the read/write split is minimal, and the kms:Decrypt is pinned with a ViaService condition.",
        "expected_top_fix": "None. Do not invent a finding. Still report the boundary.",
        "expected_boundary_join": "the other attached policies, the permissions boundary, and org SCPs (a clean policy is not a clean principal).",
    },
]


def fixture_dir(policy: dict) -> Path:
    return FIXTURES_DIR / policy["id"]


def load_fixture_text(policy: dict) -> str:
    """The raw policy JSON the agent is given: the permissions policy, plus trust / boundary if present."""
    d = fixture_dir(policy)
    parts = []
    for path in sorted(d.glob("policy*.json")):
        doc = json.loads(path.read_text())
        parts.append(f"PERMISSIONS POLICY ({path.name}):\n" + json.dumps(doc, indent=2))
    trust = d / "trust-policy.json"
    if trust.exists():
        parts.append("TRUST POLICY (AssumeRolePolicyDocument):\n" + json.dumps(json.loads(trust.read_text()), indent=2))
    boundary = d / "boundary.json"
    if boundary.exists():
        parts.append("PERMISSIONS BOUNDARY (boundary.json):\n" + json.dumps(json.loads(boundary.read_text()), indent=2))
    return "\n\n".join(parts)


def expected_audit(policy: dict) -> dict:
    """Run the deterministic reference audit to get the ground-truth findings for the judge."""
    audit = run_audit(fixture_dir(policy))
    return {
        "codes": sorted(audit.codes()),
        "top_severity": audit.top_severity,
        "clean": audit.clean,
        "boundary_count": len(audit.boundary),
    }


if __name__ == "__main__":
    # `python tests/eval/policies.py` prints the ground-truth answers, no API needed.
    for p in POLICIES:
        exp = expected_audit(p)
        print(f"{p['id']:<32} codes={str(exp['codes']):<18} top={exp['top_severity']} clean={exp['clean']}")

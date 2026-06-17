"""
Per-fixture principal contexts and expected answers, used by run_eval.py.

The ground-truth findings are NOT hand-written. The "expected_audit" function runs the
copied reference engine (_audit.py) against each fixture, so the codes / severity / clean
flag the judge is anchored to are exactly what the engine computes (see tests/replay_*.py).
The "expected_headline / fix / boundary" strings are human-readable framing for the judge
prompt; they describe the SAME verdict the engine grounds, never a different one.

This screening harness is CONTROL-ONLY: there is no SKILL.md and no treatment arm. The set
targets the cold agent's proven weak region, OVER-FLAGGING neutralised policies: six
deceptive-clean fixtures that look like critical escalation but are capped (the engine finds
nothing), each with a distinct neutralisation mechanism (explicit Deny on PassRole; Action '*'
scoped + service Deny; broken trust; a permission-boundary Deny over a full mutation kit; a
cross-account AssumeRole sealed by an unsatisfiable Condition; a PassRole whose only passable
role is read-only and whose compute verbs bind no role). One buried-hard needle is kept where a
real escalation (E1) only emerges from the union of six attached policies / ~16 statements.

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
# plus the headline / fix / boundary that match the deterministic audit's verdict (the
# judge's anchor). Keep this list aligned with the replay_*.py files under tests/.
SCENARIOS = [
    {
        "id": "01-orphaned-passrole-deny",
        "principal": "role/build-fleet-runner",
        "role": "Runs an EC2 build fleet. Granted ec2:RunInstances and, in a separate statement, iam:PassRole; a third statement is an explicit Deny on iam:PassRole.",
        "expected_headline": "No real escalation. PassRole + RunInstances looks like the classic E1 combo, but an explicit Deny on iam:PassRole (Resource '*') overrides the scoped Allow, so the PassRole half is dead and the combo cannot complete.",
        "expected_top_fix": "None on the escalation: it is already neutralised by the Deny. Optionally remove the now-inert PassRole Allow and the retired instance-profile reference to reduce confusion.",
        "expected_boundary_join": "the privileges of the roles PassRole could pass IF it were allowed (moot here), and the principal's other attached policies / permissions boundary / org SCPs.",
    },
    {
        "id": "02-action-star-blanket-deny",
        "principal": "role/sandbox-experimenter",
        "role": "An experimentation role. Granted Action '*' on a single sandbox S3 bucket, with a Deny on every escalation-bearing service (iam, sts, kms, lambda, ec2:RunInstances, ssm, secretsmanager) on Resource '*'.",
        "expected_headline": "No real escalation. Action '*' reads like AdministratorAccess, but it is pinned to one sandbox bucket (never Resource '*'), and the Deny removes every dangerous service. The star expands to nothing useful outside one scratch bucket.",
        "expected_top_fix": "None required for security: the star is already scoped and the Deny caps it. Optionally replace Action '*' with the concrete S3 actions in use for clarity.",
        "expected_boundary_join": "whether anything outside this document re-grants the denied services (other attached policies could not, since an explicit Deny wins), and the org SCPs.",
    },
    {
        "id": "03-assumerole-broken-trust",
        "principal": "role/deploy-orchestrator",
        "role": "Granted sts:AssumeRole on role/org-admin-break-glass (an admin-sounding target) and read access to a deploy-config bucket. The target role's trust policy is supplied.",
        "expected_headline": "No real escalation. sts:AssumeRole on an admin role sounds like a lateral move, but the target's trust policy only trusts two specific operator roles behind an ExternalId, not this principal, and this principal has no iam:UpdateAssumeRolePolicy to rewrite it. The path is broken.",
        "expected_top_fix": "None: the AssumeRole grant is inert because the trust does not point back. Optionally remove the unused AssumeRole grant.",
        "expected_boundary_join": "the actual contents of the target role's trust policy and whether any OTHER principal this role can reach closes the loop (confirmed broken here from the supplied trust).",
    },
    {
        "id": "05-iam-mutation-boundary-capped",
        "principal": "role/identity-platform-operator",
        "role": "An identity-platform role across two attached policies. policy-1 grants a full mutation kit (iam:PutRolePolicy, AttachRolePolicy, CreatePolicyVersion, SetDefaultPolicyVersion, UpdateAssumeRolePolicy, PassRole, CreateAccessKey) scoped to one break-glass role/policy ARN; policy-2 is a permission-boundary-style explicit Deny on every one of those actions (plus sts:AssumeRole and the credential-minting set) across Resource '*'.",
        "expected_headline": "No real escalation. policy-1 looks like a full identity-takeover kit (every E2/E4/E5/E6 primitive), but policy-2's explicit Deny on all of them across Resource '*' wins over the Allow, so the effective permission set collapses to read-only IAM inventory. The mutation kit is fully capped.",
        "expected_top_fix": "None for security: the Deny boundary already neutralises the kit. Optionally remove the now-inert mutation Allow so the policy reads honestly, and keep the Deny as the boundary.",
        "expected_boundary_join": "whether any other attached policy or the org SCPs re-grant the denied actions (they cannot, since an explicit Deny wins), and what the break-glass role/policy ARN would have permitted if the Deny were removed.",
    },
    {
        "id": "06-cross-account-assume-condition-gated",
        "principal": "role/cost-reporting-collector",
        "role": "A cost-reporting role. policy-1 grants sts:AssumeRole on a role in a DIFFERENT account (905512347781) behind an sts:ExternalId + aws:PrincipalOrgID Condition; the target role's trust policy is supplied and uses a wildcard Principal narrowed by the same org-id + ExternalId condition. The rest is read-only billing/cost access.",
        "expected_headline": "No real escalation. The cross-account sts:AssumeRole reads like a pivot into a foreign account, but it is gated by an sts:ExternalId + aws:PrincipalOrgID Condition this principal cannot satisfy, and the target's trust wildcard Principal is fully narrowed by the same condition (so no open trust). The principal has no iam:UpdateAssumeRolePolicy to relax either side. The path is condition-sealed at both ends.",
        "expected_top_fix": "None: the AssumeRole grant is inert because the condition cannot be met and the trust does not open. Optionally remove the unused cross-account AssumeRole grant.",
        "expected_boundary_join": "whether the principal can ever present the required org-id / ExternalId (it cannot from this identity), and what the foreign-account target role can do if the path were ever opened.",
    },
    {
        "id": "07-passrole-sandboxed-role-orphaned",
        "principal": "role/sandbox-compute-operator",
        "role": "A sandbox compute-operator role across three attached policies. policy-1 grants iam:PassRole scoped to one role, sandbox-readonly-compute; policy-2 grants compute verbs (ec2:StartInstances, ecs:StartTask, lambda:InvokeFunction) on existing compute; policy-3 is the passed role's OWN policy, which is strictly read-only.",
        "expected_headline": "No real escalation. iam:PassRole plus compute verbs reads like the E1 launch combo, but Start/Invoke operate on EXISTING compute and accept no PassRole argument, so there is no role-binding launch action (RunInstances/CreateFunction/RunTask) to pair PassRole with. And the one passable role is read-only, no more privileged than the caller. An orphaned escalation: the shape is there, the gain is not.",
        "expected_top_fix": "None for security: the combo cannot complete and the passed role grants nothing extra. Optionally remove the unused PassRole grant if no role-binding launch action will be added later.",
        "expected_boundary_join": "the actual privileges of sandbox-readonly-compute (confirmed read-only here from the attached policy), and whether any future policy adds a role-binding launch action that would re-arm the combo.",
    },
    {
        "id": "08-ml-platform-passrole-launch-needle",
        "principal": "role/ml-training-platform",
        "role": "A SageMaker training platform across six attached policies (~16 statements). iam:PassRole on Resource '*' is granted in one policy (framed as passing the training execution role); sagemaker:CreateTrainingJob is granted in another; the rest are routine read/queue/experiment/output permissions.",
        "expected_headline": "Real privilege escalation (critical). iam:PassRole on Resource '*' plus sagemaker:CreateTrainingJob is the E1 combo: launch a training job with ANY role in the account attached, then use that job's credentials. The two halves sit four policies apart behind heavy benign bait, so a per-statement read clears every statement; only the union is critical.",
        "expected_top_fix": "Scope iam:PassRole to the exact execution-role ARNs the training platform must pass (never '*'), with an iam:PassedToService condition pinning it to sagemaker, or remove CreateTrainingJob from this role.",
        "expected_boundary_join": "the privileges of the roles iam:PassRole can pass (not in this policy): the escalation's blast radius is whatever the most-privileged passable role can do.",
    },
]


def fixture_dir(scenario: dict) -> Path:
    return FIXTURES_DIR / scenario["id"]


def load_fixture_text(scenario: dict) -> str:
    """The raw policy JSON the agent is given: the permissions policy, plus trust / boundary if present."""
    d = fixture_dir(scenario)
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


def expected_audit(scenario: dict) -> dict:
    """Run the deterministic reference audit to get the ground-truth findings for the judge."""
    audit = run_audit(fixture_dir(scenario))
    return {
        "codes": sorted(audit.codes()),
        "top_severity": audit.top_severity,
        "clean": audit.clean,
        "boundary_count": len(audit.boundary),
    }


if __name__ == "__main__":
    # `python tests/eval/scenarios.py` prints the ground-truth answers, no API needed.
    for s in SCENARIOS:
        exp = expected_audit(s)
        print(f"{s['id']:<40} codes={str(exp['codes']):<10} top={str(exp['top_severity']):<9} clean={exp['clean']}")

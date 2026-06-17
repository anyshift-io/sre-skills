"""
Reference implementation of the iam-policy-auditor methodology.

This module is a deterministic stand-in for what an AI agent does when it
follows SKILL.md. It exists so replay tests can assert that the methodology,
applied to known IAM policy documents, produces the expected findings and the
expected boundary (the questions a single policy document alone cannot answer).

Input shape mirrors the real AWS IAM API. A permissions policy is a JSON
document with a `Statement` array; each statement carries `Effect`, `Action`
(or `NotAction`), `Resource` (or `NotResource`), and an optional `Condition`.
The skill audits the *union* of every statement across every policy document
attached to one principal, because the privilege-escalation combinations it
exists to catch are precisely the ones that span two statements (or two
separate attached policies) so that no single statement looks guilty on its own.

Stdlib only. No external dependencies. No external credentials. Runs anywhere
Python 3.10+ runs.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Services where a service-level wildcard (`<svc>:*`) hands over enough to take the
# account over by itself, or to read every secret in it. Not exhaustive; these are the
# ones whose wildcard is a finding rather than a smell.
SENSITIVE_SERVICES = {
    "iam": "identity and access management (can rewrite any permission in the account)",
    "sts": "token service (can assume roles)",
    "organizations": "the AWS Organization (SCPs, account control)",
    "kms": "the keys that decrypt everything else",
    "secretsmanager": "every stored secret",
    "ssm": "parameters and run-command on every instance",
    "s3": "every object in every bucket",
    "lambda": "function code that runs with attached roles",
    "ec2": "compute the account's roles can be passed to",
    "dynamodb": "every table's data",
}

# Compute-launch actions that accept a role via iam:PassRole. Pairing any of these with
# PassRole lets the caller hand a role more privileged than itself to compute it controls,
# then use that compute's credentials. The canonical privilege-escalation primitive.
COMPUTE_LAUNCH_ACTIONS = (
    "ec2:RunInstances",
    "lambda:CreateFunction",
    "ecs:RunTask",
    "glue:CreateDevEndpoint",
    "glue:CreateJob",
    "sagemaker:CreateNotebookInstance",
    "sagemaker:CreateTrainingJob",
    "cloudformation:CreateStack",
    "codebuild:CreateProject",
    "datapipeline:CreatePipeline",
)

# Actions that mint or reset credentials for *another* identity: a sideways takeover that
# does not touch the caller's own policies at all.
CREDENTIAL_MINTING_ACTIONS = (
    "iam:CreateAccessKey",
    "iam:CreateLoginProfile",
    "iam:UpdateLoginProfile",
    "iam:AddUserToGroup",
    "iam:CreateServiceSpecificCredential",
    "iam:ResetServiceSpecificCredential",
)

# Policy-mutation actions that let the caller grant itself (or anyone) AdministratorAccess.
POLICY_ATTACH_ACTIONS = (
    "iam:AttachUserPolicy",
    "iam:AttachRolePolicy",
    "iam:AttachGroupPolicy",
    "iam:PutUserPolicy",
    "iam:PutRolePolicy",
    "iam:PutGroupPolicy",
)

# A curated catalogue of security-relevant actions, used only to *display* what a wildcard
# expands to. It is deliberately the privilege-relevant subset of AWS, not all ~14k actions:
# a wildcard also grants many benign actions this list does not name (see the boundary).
SENSITIVE_ACTION_CATALOGUE = (
    *POLICY_ATTACH_ACTIONS,
    *CREDENTIAL_MINTING_ACTIONS,
    *COMPUTE_LAUNCH_ACTIONS,
    "iam:PassRole",
    "iam:CreatePolicyVersion",
    "iam:SetDefaultPolicyVersion",
    "iam:UpdateAssumeRolePolicy",
    "iam:CreateUser",
    "iam:CreateRole",
    "iam:DeleteRolePermissionsBoundary",
    "iam:DeleteUserPermissionsBoundary",
    "lambda:UpdateFunctionCode",
    "lambda:UpdateFunctionConfiguration",
    "lambda:AddPermission",
    "sts:AssumeRole",
    "kms:Decrypt",
    "secretsmanager:GetSecretValue",
    "ssm:GetParameter",
    "ssm:GetParameters",
    "s3:GetObject",
    "dynamodb:GetItem",
)

# Read-only "reach" actions. Resource:* on these is a data-exfiltration *surface*, but
# whether it matters depends on what lives in those resources (a data-classification
# question this document cannot answer): low severity, deferred to the boundary.
READ_REACH_ACTIONS = (
    "s3:GetObject",
    "s3:ListBucket",
    "dynamodb:GetItem",
    "dynamodb:Scan",
    "dynamodb:Query",
    "secretsmanager:GetSecretValue",
    "ssm:GetParameter",
    "ssm:GetParameters",
    "kms:Decrypt",
)

# Verbs that mark an action as mutating (used by W4's "Resource:* on a scopable write").
_MUTATING_PREFIXES = (
    "Create", "Delete", "Put", "Update", "Modify", "Attach", "Detach",
    "Write", "Set", "Remove", "Add", "Replace", "Tag", "Untag", "Terminate",
)


@dataclass
class Finding:
    """One misconfiguration, derived from the policy document(s) alone."""

    code: str          # W1..W5, E1..E6, X1
    severity: str      # critical | high | medium | low
    attribute: str     # the statement / action(s) the finding is grounded in
    title: str
    detail: str
    recommendation: str


@dataclass
class Audit:
    """Structured output of the methodology, one per principal."""

    principal: str
    statement_count: int = 0
    findings: list[Finding] = field(default_factory=list)
    # For each wildcard statement, the security-relevant concrete actions it expands to.
    expanded: dict[str, list[str]] = field(default_factory=dict)
    # The wall: questions a single policy document cannot answer. Each names a join
    # (across policies, across resources, or across the org) the audit cannot make.
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


def load_policy(path: Path) -> dict:
    """Load one policy document, accepting the common API envelopes.

    Handles: a bare policy document ({"Version", "Statement"}), the
    get-policy-version shape ({"PolicyVersion": {"Document": {...}}}), and the
    get-role-policy / get-user-policy shape ({"PolicyDocument": {...}}).
    """
    with path.open() as f:
        doc = json.load(f)
    if "PolicyVersion" in doc and isinstance(doc["PolicyVersion"], dict):
        doc = doc["PolicyVersion"].get("Document", {})
    elif "PolicyDocument" in doc:
        doc = doc["PolicyDocument"]
    elif "Document" in doc and "Statement" not in doc:
        doc = doc["Document"]
    return doc


def _statements(policy: dict) -> list[dict]:
    return [s for s in _as_list(policy.get("Statement")) if isinstance(s, dict)]


# --- Effective-permission resolution -------------------------------------------------


def _action_matches(pattern: str, action: str) -> bool:
    """Case-insensitive glob match, the way IAM matches an Action pattern."""
    return fnmatch.fnmatch(action.lower(), pattern.lower())


def _statement_allows_action(stmt: dict, action: str) -> bool:
    """True if this statement's Action / NotAction set covers `action`."""
    if "NotAction" in stmt:
        return not any(_action_matches(p, action) for p in _as_list(stmt["NotAction"]))
    return any(_action_matches(p, action) for p in _as_list(stmt.get("Action")))


@dataclass
class Resolver:
    """Resolves whether the union of statements grants an action, and on which resources.

    Deny handling is a conservative approximation: an action is denied when a Deny
    statement matches it on Resource "*" (or NotResource that excludes nothing). Real IAM
    evaluates Deny per concrete resource ARN; resource-specific denies are behind the
    boundary (this audit does not enumerate the account's ARNs). The approximation never
    *under*-reports a grant on a wildcard resource, which is the case the skill cares about.
    """

    allow_statements: list[dict]
    deny_statements: list[dict]

    def _denied(self, action: str) -> bool:
        for stmt in self.deny_statements:
            if not _statement_allows_action(stmt, action):
                continue
            resources = _as_list(stmt.get("Resource"))
            if "*" in resources or not resources:  # blanket deny
                return True
        return False

    def allows(self, action: str) -> bool:
        if self._denied(action):
            return False
        return any(_statement_allows_action(s, action) for s in self.allow_statements)

    def granted_resources(self, action: str) -> list[str]:
        """The union of Resource values on the Allow statements that grant `action`."""
        resources: list[str] = []
        for stmt in self.allow_statements:
            if _statement_allows_action(stmt, action):
                resources.extend(_as_list(stmt.get("Resource")) or ["*"])
        return resources


def _build_resolver(policies: list[dict]) -> Resolver:
    allow, deny = [], []
    for policy in policies:
        for stmt in _statements(policy):
            if stmt.get("Effect") == "Deny":
                deny.append(stmt)
            elif stmt.get("Effect") == "Allow":
                allow.append(stmt)
    return Resolver(allow_statements=allow, deny_statements=deny)


def _expand_statement(stmt: dict) -> list[str]:
    """The security-relevant concrete actions a (wildcard) statement grants."""
    return [a for a in SENSITIVE_ACTION_CATALOGUE if _statement_allows_action(stmt, a)]


# --- Statement-level wildcard checks (W1..W5) ----------------------------------------


def _is_full_wildcard_action(stmt: dict) -> bool:
    return "*" in _as_list(stmt.get("Action"))


def _has_wildcard_resource(stmt: dict) -> bool:
    resources = _as_list(stmt.get("Resource"))
    return "*" in resources or not resources and "NotResource" not in stmt


def _service_wildcards(stmt: dict) -> list[str]:
    """Service-level wildcard patterns (`svc:*`) on a sensitive service in this statement."""
    out = []
    for pat in _as_list(stmt.get("Action")):
        if isinstance(pat, str) and pat.endswith(":*"):
            svc = pat.split(":", 1)[0].lower()
            if svc in SENSITIVE_SERVICES:
                out.append(pat)
    return out


def classify_wildcards(policies: list[dict], expanded: dict[str, list[str]]) -> list[Finding]:
    """Assign each Allow statement at most one wildcard finding (W1 > W3 > W2 > W4 > W5)."""
    findings: list[Finding] = []
    idx = 0
    for policy in policies:
        for stmt in _statements(policy):
            idx += 1
            if stmt.get("Effect") != "Allow":
                continue
            sid = stmt.get("Sid") or f"statement#{idx}"
            wildcard_resource = _has_wildcard_resource(stmt)

            # W1: Action "*" on Resource "*" -> full administrator.
            if _is_full_wildcard_action(stmt) and wildcard_resource:
                expanded[sid] = _expand_statement(stmt)
                findings.append(Finding(
                    code="W1", severity="critical", attribute=f"{sid}: Action '*' on Resource '*'",
                    title="Statement grants full administrator (Action '*' on Resource '*')",
                    detail=(
                        f"Statement '{sid}' allows every action on every resource. This is "
                        "AdministratorAccess by value: the principal can do anything in the "
                        "account, including rewriting its own and everyone else's permissions. "
                        "Every privilege-escalation path below is a subset of this one grant; "
                        "it is reported as the single headline rather than enumerated."
                    ),
                    recommendation=(
                        "Replace the wildcard with the specific actions and resource ARNs the "
                        "principal actually needs. If administrator access is genuinely "
                        "intended, attach the AWS-managed AdministratorAccess policy explicitly "
                        "so the intent is auditable, and gate it behind a permissions boundary."
                    ),
                ))
                continue

            # W3: Allow + NotAction -> allow-all-except (reads narrow, grants the rest of AWS).
            if "NotAction" in stmt:
                findings.append(Finding(
                    code="W3", severity="high", attribute=f"{sid}: Effect Allow with NotAction",
                    title="Allow with NotAction grants everything except a short list",
                    detail=(
                        f"Statement '{sid}' uses Effect 'Allow' with 'NotAction'. This does not "
                        "mean 'allow these few actions' -- it means 'allow every action in AWS "
                        "except the ones listed'. The statement reads like a narrow grant and is "
                        "in fact one of the broadest possible. Allow+NotAction is almost always a "
                        "mistake; the safe shape is Deny+NotAction, or Allow+Action."
                    ),
                    recommendation=(
                        "Invert to an explicit allow-list: Effect 'Allow' with 'Action' naming "
                        "the permitted actions. Use NotAction only with Effect 'Deny'."
                    ),
                ))
                continue

            # W2: service-level wildcard on a sensitive service.
            svc_wildcards = _service_wildcards(stmt)
            if svc_wildcards:
                expanded[sid] = _expand_statement(stmt)
                services = ", ".join(f"{p} ({SENSITIVE_SERVICES[p.split(':')[0].lower()]})" for p in svc_wildcards)
                findings.append(Finding(
                    code="W2", severity="high", attribute=f"{sid}: {', '.join(svc_wildcards)}",
                    title=f"Service-level wildcard on a sensitive service ({', '.join(svc_wildcards)})",
                    detail=(
                        f"Statement '{sid}' grants {services}. A service-level wildcard hands over "
                        "every action that service exposes, including the mutating and "
                        "credential-bearing ones a checklist of named actions would never wave "
                        "through. The expanded permissions below show the security-relevant subset."
                    ),
                    recommendation=(
                        "Scope to the specific actions in use. If broad access to the service is "
                        "genuinely required, pin it to specific resource ARNs and add a Condition."
                    ),
                ))
                continue

            # W4 / W5: concrete actions on Resource "*".
            if wildcard_resource:
                concrete = [a for a in _as_list(stmt.get("Action")) if isinstance(a, str) and a != "*"]
                mutating = [a for a in concrete if ":" in a and any(a.split(":", 1)[1].startswith(v) for v in _MUTATING_PREFIXES)]
                read_reach = [a for a in READ_REACH_ACTIONS if _statement_allows_action(stmt, a)]
                if mutating:
                    findings.append(Finding(
                        code="W4", severity="medium", attribute=f"{sid}: Resource '*' on {', '.join(mutating[:4])}",
                        title="Mutating actions granted on Resource '*' where scoping is possible",
                        detail=(
                            f"Statement '{sid}' grants mutating actions ({', '.join(mutating[:6])}) "
                            "on Resource '*'. These actions support resource-level permissions, so "
                            "the wildcard is broader than the workload needs: any object/table/"
                            "function in the account is in range, not just the ones this principal "
                            "owns. Note that some AWS actions only support Resource '*'; this flags "
                            "the ones that do not have to."
                        ),
                        recommendation="Pin Resource to the specific ARNs the principal operates on; add a Condition where the action supports one.",
                    ))
                elif read_reach:
                    findings.append(Finding(
                        code="W5", severity="low", attribute=f"{sid}: Resource '*' on {', '.join(read_reach[:4])}",
                        title="Broad read access on Resource '*' (data-exfiltration reach)",
                        detail=(
                            f"Statement '{sid}' grants read/list access ({', '.join(read_reach[:6])}) "
                            "across every resource in the account. Whether that is a problem depends "
                            "on what data those resources hold -- a data-classification question this "
                            "document cannot answer (see boundary). Flagged as a low-severity reach to "
                            "verify, not a confirmed leak."
                        ),
                        recommendation="Scope read access to the specific buckets / tables / secrets the principal needs; confirm none hold data above the principal's clearance.",
                    ))
    return findings


# --- Privilege-escalation combo checks (E1..E6) --------------------------------------


def check_privesc_combos(resolver: Resolver) -> list[Finding]:
    """The flagship. Combos that span statements so no single statement looks guilty."""
    findings: list[Finding] = []

    # E1: iam:PassRole + a compute-launch action.
    if resolver.allows("iam:PassRole"):
        launchers = [a for a in COMPUTE_LAUNCH_ACTIONS if resolver.allows(a)]
        if launchers:
            passrole_resources = resolver.granted_resources("iam:PassRole")
            unscoped = "*" in passrole_resources or not passrole_resources
            severity = "critical" if unscoped else "high"
            scope_note = (
                "iam:PassRole is granted on Resource '*', so any role in the account -- "
                "including an administrator role -- can be passed."
                if unscoped else
                f"iam:PassRole is scoped to {passrole_resources}; the escalation is real only if "
                "that role is more privileged than this principal, which this document cannot "
                "show (see boundary). Reported high rather than critical for that reason."
            )
            findings.append(Finding(
                code="E1", severity=severity,
                attribute=f"iam:PassRole + {launchers[0]}",
                title="Privilege escalation: pass a role to compute the caller controls",
                detail=(
                    f"The policy allows iam:PassRole and {', '.join(launchers)}. Neither statement "
                    "is alarming alone -- passing a role is routine, and launching compute is "
                    "routine -- but together they are a textbook escalation: launch an instance / "
                    "function with a more-privileged role attached, then use that compute's "
                    f"credentials to act as the role. {scope_note}"
                ),
                recommendation=(
                    "Scope iam:PassRole to the exact role ARNs this workload must pass (never '*'), "
                    "and add an iam:PassedToService Condition pinning it to the intended service."
                ),
            ))

    # E2: rewrite an attached managed policy in place.
    if resolver.allows("iam:CreatePolicyVersion") or resolver.allows("iam:SetDefaultPolicyVersion"):
        actions = [a for a in ("iam:CreatePolicyVersion", "iam:SetDefaultPolicyVersion") if resolver.allows(a)]
        findings.append(Finding(
            code="E2", severity="critical", attribute=" / ".join(actions),
            title="Privilege escalation: rewrite a managed policy in place",
            detail=(
                f"The policy allows {' and '.join(actions)}. The principal can create a new "
                "version of any customer-managed policy (with --set-as-default) granting "
                "AdministratorAccess, or flip the default version to an older permissive one. "
                "The escalation needs no second action and leaves the policy's name and ARN "
                "unchanged, so the attached-policy list still looks identical to before."
            ),
            recommendation=(
                "Remove iam:CreatePolicyVersion / iam:SetDefaultPolicyVersion unless this is a "
                "policy-administration role, and scope the Resource to the specific policy ARNs "
                "it manages (never '*')."
            ),
        ))

    # E3: overwrite the code of a function that runs with a role.
    if resolver.allows("lambda:UpdateFunctionCode"):
        also_passrole = resolver.allows("iam:PassRole")
        findings.append(Finding(
            code="E3", severity="critical", attribute="lambda:UpdateFunctionCode",
            title="Privilege escalation: hijack a Lambda function's execution role",
            detail=(
                "The policy allows lambda:UpdateFunctionCode. Any existing function the principal "
                "can target runs with that function's execution role; overwriting its code runs "
                "attacker-chosen code with that role's permissions. "
                + (
                    "Combined with the iam:PassRole this policy also grants, the principal can "
                    "even create a fresh function with a privileged role and arm it end to end. "
                    if also_passrole else
                    "No PassRole is needed: it reuses a role already attached to an existing function. "
                )
                + "The UpdateFunctionCode statement looks like a routine deployment permission."
            ),
            recommendation=(
                "Scope lambda:UpdateFunctionCode to the specific function ARNs this principal "
                "deploys, and ensure those functions' execution roles are no more privileged than "
                "the principal itself."
            ),
        ))

    # E4: attach or inline a policy onto a principal -> grant self admin.
    attach_actions = [a for a in POLICY_ATTACH_ACTIONS if resolver.allows(a)]
    if attach_actions:
        findings.append(Finding(
            code="E4", severity="critical", attribute=", ".join(attach_actions),
            title="Privilege escalation: attach an administrator policy to a principal",
            detail=(
                f"The policy allows {', '.join(attach_actions)}. The principal can attach the "
                "AWS-managed AdministratorAccess policy (or inline an equivalent) onto itself, "
                "another user, or a role it can assume. A single attach call turns a scoped "
                "identity into an administrator, and the grant statement reads like ordinary "
                "permission-management plumbing."
            ),
            recommendation=(
                "Remove the policy-attachment actions unless this is an identity-administration "
                "role; if it must keep them, add a permissions boundary that caps what any "
                "attached policy can grant, and scope the Resource to specific principals."
            ),
        ))

    # E5: rewrite a role's trust policy, then assume it.
    if resolver.allows("iam:UpdateAssumeRolePolicy"):
        can_assume = resolver.allows("sts:AssumeRole")
        severity = "critical" if can_assume else "high"
        findings.append(Finding(
            code="E5", severity=severity, attribute="iam:UpdateAssumeRolePolicy" + (" + sts:AssumeRole" if can_assume else ""),
            title="Privilege escalation: rewrite a role's trust policy to assume it",
            detail=(
                "The policy allows iam:UpdateAssumeRolePolicy"
                + (" together with sts:AssumeRole" if can_assume else "")
                + ". The principal can rewrite the trust policy of a more-privileged role to "
                "trust itself, then assume that role and inherit its permissions. "
                + (
                    "Both halves of the escalation are present in this policy. "
                    if can_assume else
                    "sts:AssumeRole is not granted here, but the default trust often permits the "
                    "rewritten principal to assume the role through another path (see boundary). "
                )
                + "Neither statement is suspicious in isolation."
            ),
            recommendation=(
                "Remove iam:UpdateAssumeRolePolicy unless this is a role-administration identity, "
                "and scope its Resource to the roles it legitimately manages (never '*')."
            ),
        ))

    # E6: mint or reset credentials for another identity.
    minting = [a for a in CREDENTIAL_MINTING_ACTIONS if resolver.allows(a)]
    if minting:
        findings.append(Finding(
            code="E6", severity="high", attribute=", ".join(minting),
            title="Privilege escalation: mint credentials for another identity",
            detail=(
                f"The policy allows {', '.join(minting)}. The principal can create a second access "
                "key for, set a console password on, or add itself to a group belonging to a "
                "more-privileged identity, then act as that identity. This is a sideways takeover "
                "that never touches the caller's own policies, so a review of *this* principal's "
                "permissions looks clean."
            ),
            recommendation=(
                "Scope these actions to the principal's own ARN (so it can rotate only its own "
                "credentials), or remove them if credential administration is not this identity's job."
            ),
        ))

    return findings


# --- Trust-policy exposure (X1) ------------------------------------------------------


_NARROWING_CONDITION_KEYS = (
    "aws:SourceArn", "aws:SourceAccount", "aws:PrincipalOrgID",
    "aws:PrincipalAccount", "sts:ExternalId",
)


def _statement_is_narrowed(stmt: dict) -> bool:
    condition = stmt.get("Condition")
    if not isinstance(condition, dict):
        return False
    for operator_block in condition.values():
        if isinstance(operator_block, dict) and any(k in _NARROWING_CONDITION_KEYS for k in operator_block):
            return True
    return False


def _principal_is_wildcard(principal: Any) -> bool:
    if principal == "*":
        return True
    if isinstance(principal, dict):
        for value in principal.values():
            if value == "*" or (isinstance(value, list) and "*" in value):
                return True
    return False


def check_trust_policy(trust: dict | None) -> list[Finding]:
    """X1: a trust policy whose principal is a wildcard with no narrowing condition."""
    if not trust:
        return []
    findings: list[Finding] = []
    for stmt in _statements(trust):
        if stmt.get("Effect") != "Allow":
            continue
        if _principal_is_wildcard(stmt.get("Principal")) and not _statement_is_narrowed(stmt):
            findings.append(Finding(
                code="X1", severity="high", attribute="AssumeRolePolicyDocument: Principal '*'",
                title="Trust policy allows a wildcard principal with no narrowing condition",
                detail=(
                    "The role's trust policy allows Principal '*' to assume it with no "
                    "aws:PrincipalOrgID / aws:SourceAccount / sts:ExternalId condition. As written, "
                    "any AWS principal in any account can assume this role and inherit every "
                    "permission its identity policies grant. A wildcard principal *with* an "
                    "ExternalId or org condition (the cross-account vendor pattern) is fine; this "
                    "one has none."
                ),
                recommendation=(
                    "Pin the trust to specific principal ARNs, or add an aws:PrincipalOrgID / "
                    "sts:ExternalId condition that scopes who can assume the role."
                ),
            ))
            break
    return findings


# --- Boundary -------------------------------------------------------------------------


def _boundary_notes(has_boundary: bool, single_document: bool, has_passrole: bool, has_trust: bool) -> list[str]:
    notes = [
        "A principal's effective permissions are the union of every managed and inline "
        "policy attached to it. "
        + ("Only one document was audited here; the others are unseen. " if single_document else "")
        + "Join: principal to its full set of attached policies.",
        "A permissions boundary caps what any of these Allow statements can actually grant. "
        + ("No boundary document was provided, so this audit assumes none. " if not has_boundary else "")
        + "Join: principal to its permissions boundary.",
        "A Service Control Policy at the Organization or OU level can Deny actions this policy "
        "Allows, and is invisible from the account. Join: account to its organization's SCPs.",
        "An escalation that passes a role, hijacks a function, or assumes a role only matters if "
        "the target is more privileged than this principal. Those privileges live in *other* "
        "resources this document does not contain. Join: this policy to the roles and resources "
        "it references.",
    ]
    if has_passrole:
        notes.append(
            "iam:PassRole's blast radius is the set of roles it can pass and what each of those "
            "roles can do -- neither is in this document. Join: PassRole to the role catalogue."
        )
    if not has_trust:
        notes.append(
            "Whether this principal can be reached at all (who holds its keys, or what its trust "
            "policy permits to assume it) is not in a permissions policy. Join: principal to its "
            "trust policy and credential holders."
        )
    notes.append(
        "Wildcard expansion above lists only the security-relevant actions in this skill's "
        "catalogue; a wildcard also grants many benign actions not enumerated here. The catalogue "
        "is the privilege-relevant subset, not all of AWS."
    )
    return notes


# --- Orchestration --------------------------------------------------------------------


def run_audit(fixture_dir: Path) -> Audit:
    """End-to-end: load every policy document for one principal, run all checks, return the Audit.

    Loads every `policy*.json` in the fixture directory (a principal can have several
    attached policies, and the privesc combos this skill catches are exactly the ones that
    span them). Optionally loads `trust-policy.json` (enables X1) and `boundary.json`
    (suppresses the 'no boundary provided' note). A `meta.json` may carry the principal label.
    """
    policy_paths = sorted(fixture_dir.glob("policy*.json"))
    policies = [load_policy(p) for p in policy_paths]

    trust_path = fixture_dir / "trust-policy.json"
    trust = load_policy(trust_path) if trust_path.exists() else None
    boundary_path = fixture_dir / "boundary.json"
    has_boundary = boundary_path.exists()

    meta_path = fixture_dir / "meta.json"
    principal = "the audited principal"
    if meta_path.exists():
        with meta_path.open() as f:
            principal = json.load(f).get("principal", principal)

    statement_count = sum(len(_statements(p)) for p in policies)
    resolver = _build_resolver(policies)

    expanded: dict[str, list[str]] = {}
    wildcard_findings = classify_wildcards(policies, expanded)
    full_admin = any(f.code == "W1" for f in wildcard_findings)

    findings: list[Finding] = list(wildcard_findings)
    if full_admin:
        # Full administrator subsumes every narrower wildcard and every privesc combo;
        # report the one headline rather than a dozen restatements of the same grant.
        findings = [f for f in wildcard_findings if f.code == "W1"]
    else:
        findings += check_privesc_combos(resolver)
    findings += check_trust_policy(trust)

    findings.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.code))

    return Audit(
        principal=principal,
        statement_count=statement_count,
        findings=findings,
        expanded=expanded,
        boundary=_boundary_notes(
            has_boundary=has_boundary,
            single_document=len(policies) <= 1,
            has_passrole=resolver.allows("iam:PassRole"),
            has_trust=trust is not None,
        ),
    )

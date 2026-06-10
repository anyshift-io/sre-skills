# Worked example 7: rewrite a trust policy, then assume the role (E5)

Two grants that, together, let the principal hand itself any role in the account by editing who is allowed to assume it. Fixtures and replay test under `../fixtures/07-update-assume-role/` and `../tests/replay_07_update_assume_role.py`.

## Scenario

- **Principal**: `role/access-administrator`, which manages who can assume which role.
- **Symptom**: the role administers trust relationships, so it holds `iam:UpdateAssumeRolePolicy` on all roles, and a broad `sts:AssumeRole` "to test that the trust edits work".

## Step 1: parse and normalise

Two `Allow` statements:
- `ManageRoleTrust`: `iam:UpdateAssumeRolePolicy`, `iam:GetRole`, `iam:ListRoles` on `arn:aws:iam::...:role/*`.
- `AssumeManagedRoles`: `sts:AssumeRole` on `arn:aws:iam::...:role/*`.

## Step 2: expand the wildcards

No wildcard Actions. The `role/*` resource wildcard scopes *which roles*, not which actions; here it is every role in the account.

## Step 3: over-broad shapes

`sts:AssumeRole` on `role/*` is broad, but assuming roles is the job. `iam:UpdateAssumeRolePolicy` on `role/*` is a trust-administration grant. Neither is a W finding on its own.

## Step 4: privilege-escalation combinations

The effective allow set holds both halves:

- `iam:UpdateAssumeRolePolicy` — rewrite any role's trust policy. ✓
- `sts:AssumeRole` — assume any role. ✓

That is **E5 (critical)**. The escalation: pick a more-privileged role (say, an admin role), rewrite *its* trust policy to trust `access-administrator`, then assume it and inherit its permissions. Both halves are present in this one policy, so the escalation is self-contained. Even without the `sts:AssumeRole` grant the rewrite alone is dangerous (the default trust often gives another path to assume), which is why E5 fires high on the rewrite alone and critical when the assume is present too.

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| E5 | critical | `iam:UpdateAssumeRolePolicy` + `sts:AssumeRole` | Remove `iam:UpdateAssumeRolePolicy` unless this is genuinely a role-administration identity, and scope its `Resource` to the specific roles it legitimately manages (never `role/*`). Scope `sts:AssumeRole` to the roles it is meant to assume. |

## Boundary

E5 proves the principal can assume any role by rewriting trust. The damage is the privileges of the role it targets.

- An account whose most-privileged role is read-only has a small E5; one with a standing admin role has a large one. Those privileges are not in this policy. Join: the rewritable roles to their permissions.
- An SCP that denies `iam:UpdateAssumeRolePolicy` would block the rewrite. Join: account to its SCPs.

## Why this is the E5 reference

E5 is the escalation that turns "who can assume this role" into a permission the principal can grant itself. The judgment is that the ability to edit a trust policy is the ability to add yourself to it — so `iam:UpdateAssumeRolePolicy` on `role/*` is, functionally, `sts:AssumeRole` on `role/*` with one extra call.

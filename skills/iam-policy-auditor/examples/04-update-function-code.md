# Worked example 4: hijack a Lambda execution role (E3)

A deployment permission that doubles as a privilege escalation, because the thing it deploys runs with someone else's credentials. Fixtures and replay test under `../fixtures/04-update-function-code/` and `../tests/replay_04_update_function_code.py`.

## Scenario

- **Principal**: `role/lambda-deployer`, a CI role that pushes code to Lambda functions.
- **Symptom**: the role is allowed to `lambda:UpdateFunctionCode` on every function in the account, "so the pipeline can deploy any service". It also holds a scoped `iam:PassRole` for creating new functions.

## Step 1: parse and normalise

Two `Allow` statements:
- `DeployLambdas`: `lambda:UpdateFunctionCode`, `lambda:GetFunction`, `lambda:ListFunctions` on `arn:aws:lambda:...:function:*`.
- `PassLambdaExecutionRole`: `iam:PassRole` on the `lambda-exec/*` role path.

## Step 2: expand the wildcards

No wildcard Actions. The function-ARN wildcard in `Resource` scopes *which functions*, not which actions.

## Step 3: over-broad shapes

`UpdateFunctionCode` is scoped to a function-ARN pattern, not literal `Resource: "*"`, so W4 does not fire. Statement by statement: a deployer that can push code and pass an exec role. Looks like a deployer.

## Step 4: privilege-escalation combinations

`lambda:UpdateFunctionCode` is in the effective allow set. That is **E3 (critical)**. Every existing function runs with *its own* execution role; overwriting a function's code runs attacker-chosen code with that role's permissions. If any function in the account runs with a privileged role — a function that can read the production database, decrypt secrets, assume an admin role — `lambda-deployer` can overwrite that function's code and inherit those permissions. No `iam:PassRole` is needed for the hijack: it reuses a role already attached to an existing function.

This policy *also* grants `iam:PassRole`, which makes the escalation self-contained from both ends: the principal can build a fresh function with a privileged exec role and arm it, not just hijack an existing one.

## Findings

| Code | Severity | Grounded in | Fix |
|---|---|---|---|
| E3 | critical | `lambda:UpdateFunctionCode` | Scope `lambda:UpdateFunctionCode` to the specific function ARNs this pipeline deploys, and ensure those functions' execution roles are no more privileged than `lambda-deployer` itself. |

## Boundary

E3 proves the principal can run code as any targetable function's role. The blast radius is the privileges of those roles.

- A function whose execution role is least-privilege is a small E3; one whose role can assume admin is a large one. The execution roles of the in-range functions are not in this policy. Join: the function ARNs to their execution roles' privileges.
- The `iam:PassRole` half is scoped to `lambda-exec/*`; what those roles can do is, again, behind the boundary. Join: PassRole to the role catalogue.

## Why this is the E3 reference

E3 is the escalation that hides inside the most normal permission a CI role has: "deploy code". The judgment is that deploying code to a function you do not own is running code *as* that function — and the function's role, not your own, is what bounds the damage.

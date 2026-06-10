# Replay tests for `iam-policy-auditor`

Stdlib-only Python tests that exercise the audit in [`../SKILL.md`](../SKILL.md) against committed fixtures. No external credentials required.

## Running the tests

From the skill directory (`skills/iam-policy-auditor/`):

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

Each test prints `PASS` or `FAIL` and exits with the appropriate code. The current suite has 11 tests covering all twelve rules (W1–W5, E1–E6, X1), the severity model, and a clean control that asserts no false positives, totalling 64 assertions. Wire them into CI as plain `python` invocations.

## What the tests assert

Each replay test loads the fixtures for one worked example, runs the reference audit (`_audit.py`) against them, and asserts:

- The policy is parsed correctly (envelope unwrapped, statements normalised).
- The expected rule(s) fire, and only those (each example isolates a rule, except where two genuinely co-occur).
- The severity is correct — including the nuance that an *unscoped* `iam:PassRole` makes E1 critical while a PassRole scoped to one role ARN makes it high (the escalation's blast radius is then behind the boundary).
- Wildcard statements are expanded to the concrete security-relevant permissions they grant.
- The boundary is reported, and names the specific join the example depends on (the role passed, the other attached policies, the permissions boundary, the org SCPs).

A test fails when the audit regresses on any of these. Treat a failed replay test as a regression in `SKILL.md` or in the reference implementation, not a test bug.

## Fixture schema

Each example has its own fixture directory under `../fixtures/<example-slug>/`. Files are committed JSON mirroring the real IAM policy-document shape: `{"Version", "Statement": [...]}`, where each statement has `Effect`, `Action` (or `NotAction`), `Resource` (or `NotResource`), and an optional `Condition`.

| File | Required | Purpose |
|---|---|---|
| `policy.json` | yes | The principal's permissions policy. **Multiple** `policy*.json` files (e.g. `policy-1.json`, `policy-2.json`) are unioned — model a principal with several attached policies this way, which is how the cross-policy escalation combos are exercised. |
| `trust-policy.json` | for roles, when relevant | The role's `AssumeRolePolicyDocument`. Required for the X1 trust check; absent means X1 cannot fire. |
| `boundary.json` | optional | The principal's permissions boundary. Its presence suppresses the "no boundary provided" note (the audit still does not intersect against it — that is named as a boundary join). |
| `meta.json` | optional | `{"principal": "...", "note": "..."}` — a label for nicer output and a one-line scenario note. |

The reference implementation (`_audit.py`) accepts the bare policy document, the `get-policy-version` envelope (`{"PolicyVersion": {"Document": {...}}}`), and the `get-role-policy` envelope (`{"PolicyDocument": {...}}`).

Key fields the audit reads:

| Field | Used by |
|---|---|
| `Action` (string or list, glob patterns) | every W and E rule; expanded against the sensitive-action catalogue |
| `NotAction` | W3 |
| `Resource` (string or list) | W1, W4, W5; E1 severity (scoped vs `*` PassRole) |
| `Effect` (`Allow` / `Deny`) | effective allow-set resolution |
| `Principal` (trust policy) | X1 |
| `Condition` | X1 narrowing; PassRole `PassedToService` note |

## Adding a new replay test

When you contribute a new worked example to the skill:

1. Drop fixtures under `../fixtures/<example-slug>/` following the schema above.
2. Add `replay_NN_<slug>.py` in this directory, modeled on the existing eleven. Use the shared `report` helper in `_replay.py`.
3. Assert the expected findings, the severity, and that the boundary names the relevant join.
4. Run locally, commit, and reference the test in the example's markdown narrative.

A new test that does not exercise a rule, severity, or boundary join the existing tests do not exercise will fail review. The point of the replay corpus is breadth.

## Why stdlib only

Skills get adopted when they run anywhere with zero setup. A `pip install` is an adoption tax. The reference implementation uses only `json`, `fnmatch`, `pathlib`, `dataclasses`, and `typing`. If a future test requires a third-party dependency (e.g. `boto3` or `pytest`), that's a signal the skill is leaking implementation detail: the audit operates on the policy JSON, not on a live AWS connection.

## Why the reference implementation is deterministic

`_audit.py` is a deterministic stand-in for what an AI agent does when it follows `SKILL.md`. It exists so the replay tests can assert that the methodology, applied to known fixtures, produces the expected findings. A natural follow-up is to run the same fixtures through an actual LLM agent loaded with `SKILL.md` and assert it produces the same findings and names the same boundary — that is exactly what the ablation eval under [`eval/`](./eval/) does.

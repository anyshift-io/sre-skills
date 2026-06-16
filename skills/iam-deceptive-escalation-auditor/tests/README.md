# Replay tests for `iam-deceptive-escalation-auditor`

Stdlib-only Python tests that lock in the deterministic reference engine's verdict on every fixture. No external credentials required.

The engine (`_audit.py`) is copied verbatim from the original `iam-policy-auditor` engine and used here to define the deterministic ground truth that the deceptive corpus is scored against (see [`eval/`](./eval/) for the control-vs-treatment lift eval that measures the `SKILL.md`).

## Running the tests

From the skill directory (`skills/iam-deceptive-escalation-auditor/`):

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

Each test prints `PASS` or `FAIL` and exits with the appropriate code. The current suite has 7 tests: four deceptive-clean fixtures (the engine finds nothing) and three buried-hard needles (the engine finds one real escalation each), totalling 34 assertions. Wire them into CI as plain `python` invocations.

## What the tests assert

Each replay test loads the fixtures for one scenario, runs the reference audit (`_audit.py`) against them, and asserts:

- **Deceptive-clean (01–04):** the audit is clean, and the specific finding code the fixture is designed to *suppress* does NOT fire (e.g. `E1` must not fire when a `Deny` kills the PassRole; `W1` must not fire when `Action '*'` is scoped to one bucket; `X1` must not fire when the trust is narrowed; `W2` must not fire on a read-only `iam:Get*` glob).
- **Buried-hard needles (05–07):** exactly the intended escalation code fires (`E1`, `E5`, `E3`), at `critical` severity, with the combo named in the finding attribute/detail, and the statement count confirms the escalation is buried across many statements rather than sitting in one obvious one.

A test fails when the engine regresses on any of these. Because the engine is copied verbatim, a failed replay test means a fixture drifted (e.g. an edit accidentally tripped an extra rule), not that the engine is wrong.

## Ground-truth rule

The verdict is **whatever the copied engine computes** — never hand-written. Every fixture was authored, then run through `_audit.py`, and adjusted until the engine returned the intended verdict. The replay tests then pin that verdict. `python tests/eval/scenarios.py` prints the same ground truth offline with no API key.

## Fixture schema

Each scenario has its own fixture directory under `../fixtures/<slug>/`. Files are committed JSON mirroring the real IAM policy-document shape: `{"Version", "Statement": [...]}`, where each statement has `Effect`, `Action` (or `NotAction`), `Resource` (or `NotResource`), and an optional `Condition`.

| File | Required | Purpose |
|---|---|---|
| `policy.json` | yes | The principal's permissions policy. **Multiple** `policy*.json` files (e.g. `policy-1.json` … `policy-5.json`) are unioned — the buried-needle fixtures use five attached policies so the escalation combo spans them. |
| `trust-policy.json` | when relevant | The role's `AssumeRolePolicyDocument`. Used by the X1 trust check; a narrowed trust (specific ARNs / `ExternalId`) suppresses X1, which is how fixture 03 stays clean. |
| `boundary.json` | optional | The principal's permissions boundary. Its presence suppresses the "no boundary provided" note. (Not used by the current seven fixtures.) |
| `meta.json` | optional | `{"principal": "...", "note": "..."}` — a label for nicer output and a one-line scenario note explaining the trap. |

The reference engine (`_audit.py`) accepts the bare policy document, the `get-policy-version` envelope (`{"PolicyVersion": {"Document": {...}}}`), and the `get-role-policy` envelope (`{"PolicyDocument": {...}}`).

## Why stdlib only

The reference engine uses only `json`, `fnmatch`, `pathlib`, `dataclasses`, and `typing`. The replay tests add nothing beyond that. The only `pip install` in the repo is `anthropic`, isolated to `tests/eval/` for the live screening run.

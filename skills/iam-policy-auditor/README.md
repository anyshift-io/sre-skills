# iam-policy-auditor

Configuration-audit skill for the IAM policy document(s) attached to one principal.

Parses the policy JSON (the output of `get-policy-version`, `get-role-policy`, or a Terraform/CDK render), expands the wildcard Actions a human eye glosses over, and reports the over-broad grants and privilege-escalation paths that no single statement looks guilty of. Then it names the boundary: the questions a policy document alone cannot answer.

## Files in this skill

| File | What it is |
|---|---|
| [`SKILL.md`](./SKILL.md) | The methodology. This is what an AI agent loads. |
| [`examples/`](./examples/) | Eleven worked examples: one per rule plus a clean control and a scoped-escalation honesty case. |
| [`fixtures/`](./fixtures/) | Committed IAM policy documents that drive the replay tests. No external credentials required. |
| [`tests/`](./tests/) | Replay tests that exercise the audit against the fixtures. |
| [`FAILURE_MODES.md`](./FAILURE_MODES.md) | Where this skill is wrong and where the agent should escalate. |

## What it checks

| Code | Rule | Severity |
|---|---|---|
| W1 | `Action: "*"` on `Resource: "*"` (full administrator) | critical |
| W2 | Service-level wildcard on a sensitive service (`iam:*`, `s3:*`, …) | high |
| W3 | `Allow` + `NotAction` (allow everything except a list) | high |
| W4 | Mutating actions on `Resource: "*"` where scoping is possible | medium |
| W5 | Broad read on `Resource: "*"` (exfiltration reach) | low |
| E1 | `iam:PassRole` + a compute-launch action | critical / high |
| E2 | `iam:CreatePolicyVersion` / `SetDefaultPolicyVersion` | critical |
| E3 | `lambda:UpdateFunctionCode` (hijack an execution role) | critical |
| E4 | Policy attach / inline put on a principal | critical |
| E5 | `iam:UpdateAssumeRolePolicy` (+ `sts:AssumeRole`) | critical / high |
| E6 | Credential minting on another identity | high |
| X1 | Trust policy: wildcard principal, no narrowing condition | high |

The E-rules are the ones a per-statement read almost never catches: each is a privilege-escalation path that only appears when the union of statements is evaluated together, so neither statement looks guilty on its own.

## Quality bar (this skill passes all three)

- [x] Two worked examples required by the bar; this skill ships [eleven](./examples/), one per rule plus a clean control and a scoped-escalation case.
- [x] Fixture-based replay tests, runnable with no external credentials. 64 assertions across the 11 tests (`for t in tests/replay_*.py; do python "$t" || exit 1; done`).
- [x] Explicit failure-modes section ([`FAILURE_MODES.md`](./FAILURE_MODES.md)).

## Measured lift

An LLM ablation eval is committed under [`tests/eval/`](./tests/eval/). It runs an agent in two conditions — control (raw policy JSON, generic "audit this" prompt) and treatment (same JSON plus this `SKILL.md`) — against the committed fixtures, and scores both against a 7-item rubric anchored to the deterministic reference audit (`_audit.py`).

The eval has not yet been scored; the harness is committed and reproducible. Run it with `python tests/eval/run_eval.py --trials 5` (needs `ANTHROPIC_API_KEY` and `pip install anthropic`). The lift is expected to concentrate on the cross-statement escalations (a cold agent reads statements one at a time and misses the PassRole-plus-compute combo) and on the boundary section (a cold agent presents a policy read as a complete access verdict). Numbers will replace this note once scored.

## How to use

### As a Claude Code / Claude Skills user

Drop `skills/iam-policy-auditor/` into your skills directory and invoke when reviewing or hardening a policy or role. The agent reads `SKILL.md`, parses the policy, and reports findings plus the boundary. Point it at a real policy with:

```sh
# A customer-managed policy (resolve the default version first):
aws iam get-policy-version --policy-arn <arn> --version-id <vN>

# A role's inline policy and its trust policy:
aws iam get-role-policy --role-name <role> --policy-name <name>
aws iam get-role --role-name <role> --query 'Role.AssumeRolePolicyDocument'
```

Supply *every* policy attached to the principal so the escalation combos can be evaluated against the full effective allow set, plus the trust policy (for X1) and the permissions boundary (so the audit does not have to assume none). Or run it against the committed fixtures first.

### As a contributor adding a new rule or example

1. Add a fixture directory under `fixtures/<example-slug>/` with `policy.json` (and optionally `trust-policy.json`, `boundary.json`, `meta.json`), following the shape in [`tests/README.md`](./tests/README.md).
2. Add a worked example under `examples/` mirroring the existing eleven.
3. Add a replay test under `tests/replay_NN_<slug>.py` asserting the expected findings and that the boundary is reported. Use the shared `report` helper in `tests/_replay.py`.
4. Update [`SKILL.md`](./SKILL.md) and this table if the rule is new.

See the top-level [`CONTRIBUTING.md`](../../CONTRIBUTING.md) for the repo-wide bar.

## Anyshift integration (opt-in)

The audit runs vendor-neutral by default. Every boundary note this skill emits is a join it cannot make from one policy document: principal to its other attached policies, principal to its permissions boundary, account to its org SCPs, `iam:PassRole` to the privileges of the roles it can pass, principal to its trust policy and credential holders. Opting in to the [Anyshift MCP](https://www.anyshift.io) resolves those joins from a versioned resource graph, so a deferred finding (a scoped escalation, a broad read) becomes a closed one.

A measured "with vs without" delta will be published here once the MCP integration has been exercised against the replay fixtures.

## License

[Apache 2.0](../../LICENSE).

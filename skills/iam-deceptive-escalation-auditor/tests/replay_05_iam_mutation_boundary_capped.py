"""
Replay test for fixtures/05-iam-mutation-boundary-capped.

Deceptive-clean. policy-1 reads like a full identity-takeover kit: PutRolePolicy,
AttachRolePolicy, CreatePolicyVersion, SetDefaultPolicyVersion, UpdateAssumeRolePolicy,
PassRole and CreateAccessKey, every E2/E4/E5/E6 primitive in one place. But each is
scoped to a single break-glass ARN (no W4), and policy-2 carries a permission-boundary-
style explicit Deny on all of them across Resource '*'. An explicit Deny wins, so the
effective set collapses to read-only IAM inventory. A cold agent is expected to over-flag
the mutation kit as critical privilege escalation and miss that the Deny caps it.

Stdlib only. Run with: `python tests/replay_05_iam_mutation_boundary_capped.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "05-iam-mutation-boundary-capped"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)

    assertions = [
        # The blanket Deny removes every mutation/credential/assume action from the allow-set.
        (audit.clean, f"expected a clean audit (mutation kit denied), got {sorted(audit.codes())}"),
        ("E2" not in audit.codes(), "E2 must NOT fire: CreatePolicyVersion/SetDefaultPolicyVersion are denied"),
        ("E4" not in audit.codes(), "E4 must NOT fire: PutRolePolicy/AttachRolePolicy are denied"),
        ("E5" not in audit.codes(), "E5 must NOT fire: UpdateAssumeRolePolicy + sts:AssumeRole are denied"),
        ("E6" not in audit.codes(), "E6 must NOT fire: CreateAccessKey is denied"),

        # The Allow is scoped to a specific ARN, so no W4 false positive on the mutations.
        ("W4" not in audit.codes(), "W4 must NOT fire: the mutation Allow is scoped to a break-glass ARN, not Resource '*'"),
        (audit.top_severity is None, "a clean audit has no top severity"),
    ]

    return report("replay_05_iam_mutation_boundary_capped", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

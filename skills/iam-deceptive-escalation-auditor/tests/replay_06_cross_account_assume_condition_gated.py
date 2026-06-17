"""
Replay test for fixtures/06-cross-account-assume-condition-gated.

Deceptive-clean. sts:AssumeRole on a role in a DIFFERENT account reads like a
cross-account pivot. But the AssumeRole Allow is gated by an sts:ExternalId +
aws:PrincipalOrgID Condition the principal cannot satisfy, and the target role's
supplied trust policy uses a wildcard Principal that is fully narrowed by the same
org-id + ExternalId condition, so X1 does NOT fire. The principal has no
iam:UpdateAssumeRolePolicy to relax either side. The pivot is condition-sealed at
both ends. A cold agent is expected to flag the wildcard trust principal (X1) and/or
the cross-account AssumeRole as a real pivot.

Stdlib only. Run with: `python tests/replay_06_cross_account_assume_condition_gated.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "06-cross-account-assume-condition-gated"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)

    assertions = [
        # AssumeRole alone is no escalation, and the narrowed trust suppresses X1.
        (audit.clean, f"expected a clean audit (condition-gated, narrowed trust), got {sorted(audit.codes())}"),
        ("X1" not in audit.codes(), "X1 must NOT fire: the wildcard trust Principal is narrowed by aws:PrincipalOrgID + sts:ExternalId"),
        ("E5" not in audit.codes(), "E5 must NOT fire: there is no iam:UpdateAssumeRolePolicy to relax the trust"),
        (audit.top_severity is None, "a clean audit has no top severity"),
    ]

    return report("replay_06_cross_account_assume_condition_gated", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

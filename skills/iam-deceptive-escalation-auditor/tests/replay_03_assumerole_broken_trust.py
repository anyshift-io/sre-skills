"""
Replay test for fixtures/03-assumerole-broken-trust.

Deceptive-clean. The permissions policy grants sts:AssumeRole on an admin-sounding
role, which reads like a lateral move into admin. But the principal has no
iam:UpdateAssumeRolePolicy to rewrite a trust, and the trust policy supplied is
narrowed (specific principal ARNs behind an ExternalId), so X1 cannot fire and there
is no actual path. A cold agent is expected to flag the AssumeRole as an escalation.

Stdlib only. Run with: `python tests/replay_03_assumerole_broken_trust.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "03-assumerole-broken-trust"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)

    assertions = [
        # AssumeRole alone is no escalation, and the narrowed trust suppresses X1.
        (audit.clean, f"expected a clean audit (no UpdateAssumeRolePolicy, narrowed trust), got {sorted(audit.codes())}"),
        ("E5" not in audit.codes(), "E5 must NOT fire: there is no iam:UpdateAssumeRolePolicy to rewrite the trust"),
        ("X1" not in audit.codes(), "X1 must NOT fire: the trust principal is narrowed (specific ARNs + ExternalId)"),
        (audit.top_severity is None, "a clean audit has no top severity"),
    ]

    return report("replay_03_assumerole_broken_trust", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

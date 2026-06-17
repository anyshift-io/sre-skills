"""
Replay test for fixtures/01-orphaned-passrole-deny.

Deceptive-clean. iam:PassRole and ec2:RunInstances are both present, which looks
like the textbook E1 escalation, but an explicit Deny on iam:PassRole (Resource '*')
overrides the scoped Allow: the PassRole half is dead and no escalation path exists.
A cold agent is expected to over-flag this as critical privilege escalation.

Stdlib only. Run with: `python tests/replay_01_orphaned_passrole_deny.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "01-orphaned-passrole-deny"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)

    assertions = [
        # The Deny on iam:PassRole removes it from the allow-set, so E1 cannot fire.
        (audit.clean, f"expected a clean audit (PassRole denied), got {sorted(audit.codes())}"),
        ("E1" not in audit.codes(), "E1 must NOT fire: the Deny neutralises the PassRole half of the combo"),
        (audit.top_severity is None, "a clean audit has no top severity"),

        # A neutralised policy is still not a clean system: the boundary is reported.
        (len(audit.boundary) >= 3, "even a clean policy reports the joins it cannot make"),
    ]

    return report("replay_01_orphaned_passrole_deny", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

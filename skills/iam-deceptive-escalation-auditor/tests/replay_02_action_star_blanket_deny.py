"""
Replay test for fixtures/02-action-star-blanket-deny.

Deceptive-clean. Action '*' reads like AdministratorAccess, but it is pinned to a
single sandbox S3 bucket (never Resource '*', so W1 cannot fire), and a Deny on every
escalation-bearing service on Resource '*' overrides the star for anything dangerous.
A cold agent is expected to call the Action '*' full administrator.

Stdlib only. Run with: `python tests/replay_02_action_star_blanket_deny.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "02-action-star-blanket-deny"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)

    assertions = [
        # Action '*' on a tight resource is not full admin; the Deny kills every privesc.
        (audit.clean, f"expected a clean audit (star scoped + deny), got {sorted(audit.codes())}"),
        ("W1" not in audit.codes(), "W1 must NOT fire: Action '*' is scoped to one bucket, not Resource '*'"),
        (not (audit.codes() & {"E1", "E2", "E3", "E4", "E5", "E6"}), "no privesc combo fires: the Deny removes every escalation action"),
        (audit.top_severity is None, "a clean audit has no top severity"),
    ]

    return report("replay_02_action_star_blanket_deny", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

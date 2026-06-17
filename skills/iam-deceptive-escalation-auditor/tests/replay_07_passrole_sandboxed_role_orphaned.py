"""
Replay test for fixtures/07-passrole-sandboxed-role-orphaned.

Deceptive-clean. iam:PassRole and a fistful of compute verbs (ec2:StartInstances,
ecs:StartTask, lambda:InvokeFunction) read like the textbook PassRole + launch
escalation. But none of those verbs is a role-binding launch primitive: Start/Invoke
operate on EXISTING compute and accept no iam:PassRole argument, so E1 has no
RunInstances/CreateFunction/RunTask to pair with. And PassRole is scoped to one role,
sandbox-readonly-compute, whose own (read-only) policy is attached here, so the passed
role is no more privileged than the caller. An orphaned escalation: the shape is there,
the privilege gain is not. A cold agent is expected to over-flag PassRole + "launch
compute" as an E1 critical.

Stdlib only. Run with: `python tests/replay_07_passrole_sandboxed_role_orphaned.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "07-passrole-sandboxed-role-orphaned"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)

    assertions = [
        # PassRole is present but no role-binding launch action is, so E1 cannot fire.
        (audit.clean, f"expected a clean audit (no role-binding launcher, read-only passed role), got {sorted(audit.codes())}"),
        ("E1" not in audit.codes(), "E1 must NOT fire: Start/Invoke are not role-binding launch actions"),
        ("E3" not in audit.codes(), "E3 must NOT fire: there is no lambda:UpdateFunctionCode"),

        # The compute verbs are scoped to specific ARNs, so no W4 false positive.
        ("W4" not in audit.codes(), "W4 must NOT fire: the compute verbs are scoped to specific ARNs"),
        (audit.top_severity is None, "a clean audit has no top severity"),
    ]

    return report("replay_07_passrole_sandboxed_role_orphaned", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

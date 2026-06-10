"""
Replay test for examples/06-attach-policy-self.md.

A single attach call turns a scoped identity into an administrator.

Stdlib only. Run with: `python tests/replay_06_attach_policy_self.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "06-attach-policy-self"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    e4 = next((f for f in audit.findings if f.code == "E4"), None)

    assertions = [
        (e4 is not None, f"expected E4 (attach admin policy), got {sorted(audit.codes())}"),
        (e4 is not None and e4.severity == "critical", "E4 must be critical"),
        (audit.codes() == {"E4"}, f"expected exactly {{E4}}, got {sorted(audit.codes())}"),

        (e4 is not None and "AttachRolePolicy" in e4.attribute, "E4 should name the attach action"),
        (e4 is not None and "AdministratorAccess" in e4.detail, "E4 detail should make the self-grant-admin path explicit"),
        # Resource scoping to a role path does not save it; the recommendation says so via a boundary.
        (e4 is not None and "boundary" in e4.recommendation.lower(), "E4 recommendation should reach for a permissions boundary"),
    ]

    return report("replay_06_attach_policy_self", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

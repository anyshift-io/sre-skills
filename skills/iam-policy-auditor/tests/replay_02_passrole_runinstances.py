"""
Replay test for examples/02-passrole-runinstances.md.

The flagship cross-statement combo: neither statement is alarming alone.

Stdlib only. Run with: `python tests/replay_02_passrole_runinstances.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "02-passrole-runinstances"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    e1 = next((f for f in audit.findings if f.code == "E1"), None)

    assertions = [
        # The combo fires even though each statement (RunInstances; PassRole) is routine alone.
        (e1 is not None, f"expected E1 (PassRole + compute), got {sorted(audit.codes())}"),
        (audit.codes() == {"E1"}, f"expected exactly {{E1}}, got {sorted(audit.codes())}"),

        # PassRole is on Resource '*', so any role can be passed: critical, not high.
        (e1 is not None and e1.severity == "critical", "unscoped PassRole ('*') must make E1 critical"),
        (e1 is not None and "RunInstances" in e1.attribute, "E1 attribute should name the launch action it pairs PassRole with"),
        (e1 is not None and "iam:PassRole" in e1.detail, "E1 detail should explain the PassRole half of the combo"),

        # The boundary names the PassRole join (what the passed role can actually do).
        (any("PassRole" in b for b in audit.boundary), "boundary should name the PassRole-to-role-catalogue join"),
    ]

    return report("replay_02_passrole_runinstances", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

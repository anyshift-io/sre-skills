"""
Replay test for examples/07-update-assume-role.md.

Rewrite a role's trust policy to trust yourself, then assume it.

Stdlib only. Run with: `python tests/replay_07_update_assume_role.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "07-update-assume-role"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    e5 = next((f for f in audit.findings if f.code == "E5"), None)

    assertions = [
        (e5 is not None, f"expected E5 (rewrite trust + assume), got {sorted(audit.codes())}"),
        # Both halves present (UpdateAssumeRolePolicy AND sts:AssumeRole) -> critical.
        (e5 is not None and e5.severity == "critical", "with sts:AssumeRole also granted, E5 must be critical"),
        (audit.codes() == {"E5"}, f"expected exactly {{E5}}, got {sorted(audit.codes())}"),

        (e5 is not None and "UpdateAssumeRolePolicy" in e5.attribute, "E5 should name the trust-editing action"),
        (e5 is not None and "sts:AssumeRole" in e5.attribute, "E5 attribute should record that the assume half is present"),
    ]

    return report("replay_07_update_assume_role", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

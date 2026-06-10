"""
Replay test for examples/01-admin-star.md.

Stdlib only. Run with: `python tests/replay_01_admin_star.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "01-admin-star"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    w1 = next((f for f in audit.findings if f.code == "W1"), None)

    assertions = [
        # Action '*' on Resource '*' is full administrator: the single critical headline.
        (w1 is not None, f"expected W1 (full admin), got {sorted(audit.codes())}"),
        (w1 is not None and w1.severity == "critical", "W1 must be critical"),
        (audit.codes() == {"W1"}, f"full admin subsumes the privesc combos; expected just {{W1}}, got {sorted(audit.codes())}"),

        # The wildcard is expanded to concrete security-relevant permissions for the reader.
        ("DevConvenience" in audit.expanded, "expected the wildcard statement to be expanded"),
        ("iam:CreatePolicyVersion" in audit.expanded.get("DevConvenience", []), "expansion should surface iam:CreatePolicyVersion as one concrete grant"),
        ("iam:PassRole" in audit.expanded.get("DevConvenience", []), "expansion should surface iam:PassRole"),

        # Even a clean-looking single statement still reports the boundary.
        (len(audit.boundary) >= 3, "a finding still names the joins it cannot make"),
    ]

    return report("replay_01_admin_star", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

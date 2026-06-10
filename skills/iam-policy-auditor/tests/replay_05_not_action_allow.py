"""
Replay test for examples/05-not-action-allow.md.

Allow + NotAction: reads like a narrow grant, is one of the broadest possible.

Stdlib only. Run with: `python tests/replay_05_not_action_allow.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "05-not-action-allow"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    w3 = next((f for f in audit.findings if f.code == "W3"), None)

    assertions = [
        (w3 is not None, f"expected W3 (Allow + NotAction), got {sorted(audit.codes())}"),
        (w3 is not None and w3.severity == "high", "W3 must be high"),
        (audit.codes() == {"W3"}, f"the NotAction excludes the escalation-bearing services here; expected just {{W3}}, got {sorted(audit.codes())}"),

        (w3 is not None and "NotAction" in w3.attribute, "W3 should name the NotAction shape"),
        (w3 is not None and "except" in w3.detail.lower(), "W3 detail should make the allow-everything-except inversion explicit"),
        (w3 is not None and "Deny" in w3.recommendation, "W3 recommendation should point at Deny+NotAction or Allow+Action"),
    ]

    return report("replay_05_not_action_allow", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

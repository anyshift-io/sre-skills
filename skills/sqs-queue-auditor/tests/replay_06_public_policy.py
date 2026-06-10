"""
Replay test for examples/06-public-queue-policy.md.

Stdlib only. Run with: `python tests/replay_06_public_policy.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "06-public-queue-policy"


def main() -> int:
    audit = run_audit(FIXTURE_DIR, is_processing_queue=True)
    r7 = next((f for f in audit.findings if f.code == "R7"), None)

    assertions = [
        # R7: wildcard principal with no narrowing condition (a public queue).
        (r7 is not None, f"expected R7 (open resource policy), got {sorted(audit.codes())}"),
        (r7 is not None and r7.severity == "high", "R7 should be high severity"),

        # R8 also fires: SqsManagedSseEnabled is false and no KMS key.
        ("R8" in audit.codes(), f"expected R8 (encryption off), got {sorted(audit.codes())}"),
        (audit.codes() == {"R7", "R8"}, f"expected exactly {{R7, R8}}, got {sorted(audit.codes())}"),

        # The audit must name the IAM-union boundary: the resource policy is only half the story.
        (any("iam" in b.lower() for b in audit.boundary), "boundary must name the IAM identity-policy union"),
    ]

    return report("replay_06_public_policy", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

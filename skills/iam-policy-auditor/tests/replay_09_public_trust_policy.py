"""
Replay test for examples/09-public-trust-policy.md.

The permissions policy is clean; the trust policy is wide open. The skill reads both.

Stdlib only. Run with: `python tests/replay_09_public_trust_policy.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "09-public-trust-policy"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    x1 = next((f for f in audit.findings if f.code == "X1"), None)

    assertions = [
        (x1 is not None, f"expected X1 (open trust policy), got {sorted(audit.codes())}"),
        (x1 is not None and x1.severity == "high", "X1 must be high"),
        # The permissions policy is scoped to one bucket: no permission finding at all.
        (audit.codes() == {"X1"}, f"the permissions policy is clean; expected just {{X1}}, got {sorted(audit.codes())}"),

        (x1 is not None and "Principal" in x1.attribute, "X1 should be grounded in the trust policy's Principal"),
        # The skill must not flag a wildcard that IS narrowed (the cross-account vendor pattern).
        (x1 is not None and ("ExternalId" in x1.detail or "PrincipalOrgID" in x1.detail), "X1 detail should contrast against the legitimately-narrowed wildcard"),
    ]

    return report("replay_09_public_trust_policy", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

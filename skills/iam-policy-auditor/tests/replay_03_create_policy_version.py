"""
Replay test for examples/03-create-policy-version.md.

A single-action escalation that rewrites the policy itself, hidden among routine reads.

Stdlib only. Run with: `python tests/replay_03_create_policy_version.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "03-create-policy-version"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    e2 = next((f for f in audit.findings if f.code == "E2"), None)

    assertions = [
        (e2 is not None, f"expected E2 (rewrite managed policy), got {sorted(audit.codes())}"),
        (e2 is not None and e2.severity == "critical", "E2 must be critical"),
        (audit.codes() == {"E2"}, f"the s3:GetObject read is correctly scoped; expected just {{E2}}, got {sorted(audit.codes())}"),

        # The escalation needs no second action and leaves the policy ARN unchanged.
        (e2 is not None and "CreatePolicyVersion" in e2.attribute, "E2 should name the policy-versioning action"),
        (e2 is not None and ("default" in e2.detail.lower() or "AdministratorAccess" in e2.detail), "E2 detail should explain the set-default-version escalation"),
    ]

    return report("replay_03_create_policy_version", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

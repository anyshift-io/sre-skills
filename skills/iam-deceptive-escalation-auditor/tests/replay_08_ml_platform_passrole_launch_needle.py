"""
Replay test for fixtures/08-ml-platform-passrole-launch-needle.

Buried-hard needle. Six attached policies for a SageMaker training platform, ~16
statements, every one plausible. The escalation is split: policy-4 grants iam:PassRole
on Resource '*' (framed as passing the training execution role), policy-6 grants
sagemaker:CreateTrainingJob (a real role-binding launch action). Composed, they are the
E1 critical: launch a training job with ANY role attached, then use its credentials.
The two halves sit four policies apart behind heavy benign bait; a per-statement read
clears every statement, only the union is critical. This is the genuine needle the screen
keeps.

Stdlib only. Run with: `python tests/replay_08_ml_platform_passrole_launch_needle.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _audit import run_audit  # noqa: E402
from _replay import report  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "08-ml-platform-passrole-launch-needle"


def main() -> int:
    audit = run_audit(FIXTURE_DIR)
    e1 = next((f for f in audit.findings if f.code == "E1"), None)

    assertions = [
        # The combo emerges only from the union of two separate attached policies.
        (e1 is not None, f"expected E1 (PassRole + compute launch), got {sorted(audit.codes())}"),
        (audit.codes() == {"E1"}, f"expected exactly {{E1}}, got {sorted(audit.codes())}"),

        # PassRole is on Resource '*', so any role can be passed: critical, not high.
        (e1 is not None and e1.severity == "critical", "unscoped PassRole ('*') must make E1 critical"),
        (e1 is not None and "CreateTrainingJob" in e1.attribute, "E1 attribute should name the launch action it pairs PassRole with"),

        # The cross-policy combo spans many statements; the engine unions them.
        (audit.statement_count >= 14, "this needle buries the combo across six policies / many statements"),

        # The boundary names the PassRole join (what the passed role can actually do).
        (any("PassRole" in b for b in audit.boundary), "boundary should name the PassRole-to-role-catalogue join"),
    ]

    return report("replay_08_ml_platform_passrole_launch_needle", audit, assertions)


if __name__ == "__main__":
    sys.exit(main())

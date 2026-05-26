"""
Replay test for examples/08-deploy-correlator-confirmation-bias.md.

Stdlib only. Run with: `python tests/replay_08_confirmation_bias.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "08-deploy-correlator-confirmation-bias"


def main() -> int:
    # Failing surface hints point at auth / secret retrieval. The deploy diff does NOT
    # touch this surface; the IAM change does. M4 guard should ensure deploy-correlator
    # is rejected.
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-07-11T14:33:00Z",
        tnow_iso="2026-07-11T14:38:00Z",
        failing_surface_hints=["secret", "auth", "iam"],
    )

    assertions = [
        # Step 2: both changes in window (deploy + IAM).
        (len(inv.change_surface) == 2, f"expected 2 changes in window, got {len(inv.change_surface)}"),

        # Step 3: NOT classified as deploy-correlator (M4 guard).
        (inv.classified_path != "deploy-correlator", f"M4 guard failed: classified as deploy-correlator despite mismatched diff surface"),

        # Should classify as outside-reference-paths (no reference path covers IAM-correlator).
        (inv.classified_path == "outside-reference-paths", f"expected outside-reference-paths, got {inv.classified_path}"),

        # Step 6: NO revert of the deploy should be in mitigation list.
        (not any(m["action"] == "revert" and "users-api" in m.get("target", "") for m in inv.mitigation_ranked), "must NOT recommend reverting the (innocent) deploy"),

        # Step 7: ESCALATE with M1 (outside paths).
        (inv.escalate_to_human is True, "must escalate per M1"),
        (any("M1" in r for r in inv.escalation_reasons), f"expected M1 in reasons, got {inv.escalation_reasons}"),

        # Confirming signals should include change_audit for the IAM change.
        (any(s["source"] == "change_audit" for s in inv.confirming_signals), f"expected change_audit signal for the IAM change, got sources {[s['source'] for s in inv.confirming_signals]}"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_08_confirmation_bias")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_08_confirmation_bias ({len(assertions)} assertions)")
    print(f"  classified_path: {inv.classified_path}")
    print(f"  escalate:        {inv.escalate_to_human} ({', '.join(inv.escalation_reasons)})")
    print(f"  M4 guard:        deploy correctly NOT classified as the cause despite timing")
    return 0


if __name__ == "__main__":
    sys.exit(main())

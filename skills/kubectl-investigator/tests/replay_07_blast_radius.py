"""
Replay test for examples/07-blast-radius-asymmetric-revert.md.

Stdlib only. Run with: `python tests/replay_07_blast_radius.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "07-blast-radius-asymmetric-revert"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-06-02T10:03:00Z",
        tnow_iso="2026-06-02T10:10:00Z",
        failing_surface_hints=["twilio", "sms"],
    )

    assertions = [
        # Step 2: one change in window, with bundle_size > 1.
        (len(inv.change_surface) == 1, f"expected 1 change in window, got {len(inv.change_surface)}"),
        (inv.change_surface[0].get("bundle_size") == 6, f"expected bundle_size=6, got {inv.change_surface[0].get('bundle_size')}"),

        # Step 3: classified as deploy-correlator.
        (inv.classified_path == "deploy-correlator", f"expected deploy-correlator, got {inv.classified_path}"),

        # Step 6: revert is still the top mitigation (methodology surfaces it).
        (inv.mitigation_ranked[0]["action"] == "revert", f"expected revert as top mitigation, got {inv.mitigation_ranked[0]['action']}"),

        # Step 7: ESCALATE because of M3 (bundle_size > 1).
        (inv.escalate_to_human is True, "must escalate when bundle_size > 1 on a revert-recommended path"),
        (any("M3" in r for r in inv.escalation_reasons), f"expected M3 escalation reason, got {inv.escalation_reasons}"),
        (any("6" in r for r in inv.escalation_reasons), f"expected M3 reason to mention 6 changes, got {inv.escalation_reasons}"),

        # Handoff carries the escalation explicitly.
        (inv.handoff["escalate_to_human"] is True, "handoff must carry escalate_to_human=True"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_07_blast_radius")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_07_blast_radius ({len(assertions)} assertions)")
    print(f"  classified_path: {inv.classified_path}")
    print(f"  recommended:     {inv.mitigation_ranked[0]['action']} (escalated: {inv.escalate_to_human})")
    print(f"  escalation:      {', '.join(inv.escalation_reasons)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

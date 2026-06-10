"""
Replay test for examples/05-outside-reference-paths-third-party-rate-limit.md.

Stdlib only. Run with: `python tests/replay_05_outside_paths.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _methodology import run_investigation  # noqa: E402

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "05-outside-reference-paths-third-party-rate-limit"


def main() -> int:
    inv = run_investigation(
        fixture_dir=FIXTURE_DIR,
        t0_iso="2026-05-04T16:44:00Z",
        tnow_iso="2026-05-04T16:50:00Z",
    )

    assertions = [
        (inv.window[0].isoformat() == "2026-05-04T16:29:00+00:00", f"window start expected 16:29:00Z, got {inv.window[0].isoformat()}"),

        # Step 2: zero changes in window.
        (len(inv.change_surface) == 0, f"expected 0 changes in window, got {len(inv.change_surface)}"),

        # Step 3: outside reference paths (no OOM, no DNS, no cascade signature, no deploy).
        (inv.classified_path == "outside-reference-paths", f"expected outside-reference-paths, got {inv.classified_path}"),

        # Step 6: no revert proposed (no change to revert).
        (not any(m["action"] == "revert" for m in inv.mitigation_ranked), "should NOT recommend revert when no change in window"),

        # Step 7: ESCALATE per M1.
        (inv.escalate_to_human is True, "outside-reference-paths must escalate per M1"),
        (any("M1" in r for r in inv.escalation_reasons), f"expected M1 escalation reason, got {inv.escalation_reasons}"),

        # Handoff should mark escalation explicitly.
        (inv.handoff["escalate_to_human"] is True, "handoff payload must carry escalate_to_human=True"),
        (inv.handoff["classified_path"] == "outside-reference-paths", "handoff classification must be outside-reference-paths"),
    ]

    failed = [msg for ok, msg in assertions if not ok]
    if failed:
        print("FAIL: replay_05_outside_paths")
        for msg in failed:
            print(f"  - {msg}")
        return 1

    print(f"PASS: replay_05_outside_paths ({len(assertions)} assertions)")
    print(f"  classified_path: {inv.classified_path}")
    print(f"  escalate:        {inv.escalate_to_human} ({', '.join(inv.escalation_reasons)})")
    print(f"  signals:         {len(inv.confirming_signals)} from {len({s['source'] for s in inv.confirming_signals})} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
